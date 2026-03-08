"""
Management command to retry failed Celery tasks from TaskFailureLog.

Usage:
    python manage.py retry_failed_tasks
    python manage.py retry_failed_tasks --task-id abc123def456
    python manage.py retry_failed_tasks --error-type RATE_LIMITED
    python manage.py retry_failed_tasks --dry-run
"""

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from cards.models import TaskFailureLog
from cards.tasks import import_card_task, scrape_card_task
from celery import current_app
import logging

logger = logging.getLogger('cards.tasks')


class Command(BaseCommand):
    help = "Retry failed Celery tasks from the dead-letter queue"

    def add_arguments(self, parser):
        parser.add_argument(
            '--task-id',
            type=str,
            help='Retry specific task by ID',
        )
        parser.add_argument(
            '--error-type',
            type=str,
            choices=['RATE_LIMITED', 'TIMEOUT', 'SERVICE_UNAVAILABLE', 'CONNECTION_ERROR'],
            help='Retry tasks of specific error type',
        )
        parser.add_argument(
            '--unresolved',
            action='store_true',
            help='Retry all unresolved tasks',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show which tasks would be retried (no action)',
        )
        parser.add_argument(
            '--max-retries',
            type=int,
            default=None,
            help='Only retry tasks with attempt_count < this value',
        )

    def handle(self, *args, **options):
        # Build query
        filters = Q(is_retryable=True, is_resolved=False)

        if options['task_id']:
            filters &= Q(task_id=options['task_id'])
        if options['error_type']:
            filters &= Q(error_type=options['error_type'])
        if options['max_retries']:
            filters &= Q(attempt_count__lt=options['max_retries'])

        failed_logs = TaskFailureLog.objects.filter(filters)
        count = failed_logs.count()

        if count == 0:
            self.stdout.write(self.style.WARNING("Aucune tâche à retenter trouvée"))
            return

        self.stdout.write(f"Trouvé {count} tâche(s) à retenter")

        if options['dry_run']:
            self.stdout.write(self.style.SUCCESS("DRY RUN - Tâches qui seraient retentées :"))
            for log in failed_logs:
                self.stdout.write(f"  - {log.task_name} ({log.error_type}) - Tentative {log.attempt_count}")
            return

        # Actually retry tasks
        retried = 0
        errors = 0

        for log in failed_logs:
            try:
                self._retry_task(log)
                log.attempt_count += 1
                log.save(update_fields=['attempt_count'])
                retried += 1
                self.stdout.write(
                    self.style.SUCCESS(f"✓ Retented: {log.task_name} (attempt #{log.attempt_count})")
                )
            except Exception as e:
                errors += 1
                self.stdout.write(
                    self.style.ERROR(f"✗ Error retrying {log.task_name}: {str(e)}")
                )
                logger.error(f"Failed to retry task {log.task_id}: {str(e)}")

        self.stdout.write(
            self.style.SUCCESS(f"\nRésumé: {retried} retentée(s), {errors} erreur(s)")
        )

    def _retry_task(self, log: TaskFailureLog):
        """Re-queue a failed task."""
        # Map task names to their functions
        task_map = {
            'cards.tasks.import_card_task': import_card_task,
            'cards.tasks.scrape_card_task': scrape_card_task,
        }

        task_fn = task_map.get(log.task_name)
        if not task_fn:
            # Fallback: try to get task from Celery registry
            try:
                task_fn = current_app.tasks[log.task_name]
            except KeyError:
                raise CommandError(f"Unknown task: {log.task_name}")

        # Re-queue with stored args/kwargs
        task_fn.delay(*log.task_args, **log.task_kwargs)
