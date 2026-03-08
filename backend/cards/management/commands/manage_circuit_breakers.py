from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from cards.models import Store, StoreCircuitBreaker


class Command(BaseCommand):
    help = 'Gere les circuit breakers des magasins'

    def add_arguments(self, parser):
        parser.add_argument(
            '--init',
            action='store_true',
            help='Initialiser les circuit breakers pour tous les stores',
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Afficher le statut des circuit breakers',
        )
        parser.add_argument(
            '--reset',
            action='store_true',
            help='Remettre tous les circuit breakers en CLOSED',
        )

    def handle(self, *args, **options):
        if options['init']:
            self.init_circuit_breakers()
        elif options['status']:
            self.show_status()
        elif options['reset']:
            self.reset_all()
        else:
            self.show_status()

    def init_circuit_breakers(self):
        """Creer les circuit breakers pour tous les stores actifs."""
        stores = Store.objects.filter(is_active=True)
        created_count = 0

        for store in stores:
            cb, created = StoreCircuitBreaker.objects.get_or_create(store=store)
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'[CREATED] {store.name}'))
            else:
                self.stdout.write(f'[EXISTS] {store.name}')

        self.stdout.write(
            self.style.SUCCESS(f'\n[OK] {created_count} circuit breakers crees/verifies')
        )

    def show_status(self):
        """Afficher le statut de tous les circuit breakers."""
        cbs = StoreCircuitBreaker.objects.all().select_related('store')

        if not cbs.exists():
            self.stdout.write(self.style.WARNING('Aucun circuit breaker configure'))
            return

        self.stdout.write('\n' + '=' * 80)
        self.stdout.write('CIRCUIT BREAKER STATUS')
        self.stdout.write('=' * 80 + '\n')

        for cb in cbs.order_by('store__name'):
            state_color = {
                'closed': self.style.SUCCESS,
                'open': self.style.ERROR,
                'half_open': self.style.WARNING,
            }.get(cb.state, self.style.WARNING)

            state_str = state_color(f'[{cb.state.upper()}]')
            errors_str = f'{cb.error_count}/{cb.error_threshold}'

            self.stdout.write(f'{state_str} {cb.store.name}')
            self.stdout.write(f'       Errors: {errors_str} | Total: {cb.total_errors} | Recovered: {cb.recovered_count}')

            if cb.last_error_at:
                elapsed = timezone.now() - cb.last_error_at
                self.stdout.write(f'       Last error: {elapsed.total_seconds():.0f}s ago')

            if cb.state == 'open' and cb.last_error_at:
                timeout_left = cb.timeout_seconds - elapsed.total_seconds()
                if timeout_left > 0:
                    self.stdout.write(f'       Recovery in: {timeout_left:.0f}s')

            self.stdout.write('')

        # Statistiques
        closed = cbs.filter(state='closed').count()
        open_count = cbs.filter(state='open').count()
        half_open = cbs.filter(state='half_open').count()

        self.stdout.write('=' * 80)
        self.stdout.write(
            f'Summary: {closed} CLOSED | {open_count} OPEN | {half_open} HALF_OPEN'
        )
        self.stdout.write('=' * 80 + '\n')

    def reset_all(self):
        """Remettre tous les circuit breakers en CLOSED."""
        cbs = StoreCircuitBreaker.objects.all()
        count = cbs.update(
            state='closed',
            error_count=0,
            opened_at=None,
            closed_at=timezone.now(),
        )

        self.stdout.write(
            self.style.SUCCESS(f'[OK] {count} circuit breakers remis en CLOSED')
        )
