import os
from celery import Celery
from celery.signals import task_failure

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('mtg_tracker')
app.config_from_object('django.conf:settings', namespace='CELERY')

# Windows compatibility: use threads pool for parallelism without prefork issues
if os.name == 'nt':  # Windows
    app.conf.worker_pool = 'threads'
    app.conf.worker_prefetch_multiplier = 1
    app.conf.worker_max_tasks_per_child = 1000

app.autodiscover_tasks()


# Signal handlers for task failure logging (dead-letter queue)
@task_failure.connect
def task_failure_handler(sender, task_id, exception, args, kwargs, traceback, einfo, **kw):
    """
    Enregistre les tâches Celery failées dans TaskFailureLog (dead-letter queue).

    Appelé quand une tâche échoue définitivement (après tous les retries).
    """
    from django.db import connection
    from cards.retry_utils import categorize_error

    # Éviter les imports circulaires en les faisant here
    try:
        from cards.models import TaskFailureLog
    except ImportError:
        return  # Django pas initialisé encore

    # Catégoriser l'erreur
    error_type, is_retryable = categorize_error(exception)

    # Limiter le traceback à 4000 chars pour la DB
    tb_str = str(einfo) if einfo else str(traceback) if traceback else ''
    tb_str = tb_str[:4000]

    try:
        TaskFailureLog.objects.create(
            task_name=sender.name,
            task_id=task_id,
            task_args=list(args),
            task_kwargs=kwargs,
            error_type=error_type,
            error_message=str(exception)[:500],
            traceback=tb_str,
            attempt_count=sender.request.retries + 1 if hasattr(sender, 'request') else 1,
            max_retries=3,  # Default, peut être customisé par tâche
            is_retryable=is_retryable,
        )
    except Exception as e:
        # Ne pas crasher si enregistrement échoue
        import logging
        logger = logging.getLogger('cards.tasks')
        logger.error(f"Failed to log task failure for {sender.name}: {str(e)}")
