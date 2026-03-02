from django.core.management.base import BaseCommand
from cards.models import Card, Store, CardPrice


CONDITION_MIGRATION = {
    'Near Mint': 'NM',
    'Lightly Played': 'LP',
    'Moderately Played': 'MP',
    'Heavily Played': 'HP',
    'Damaged': 'DMG',
}

LANGUAGE_MIGRATION = {
    'English': 'EN',
    'French': 'FR',
    'German': 'DE',
    'Spanish': 'ES',
    'Italian': 'IT',
    'Japanese': 'JP',
}

VALID_CONDITIONS = {'NM', 'LP', 'MP', 'HP', 'DMG'}
VALID_LANGUAGES = {'EN', 'FR', 'DE', 'ES', 'IT', 'JP', 'PHY', 'KO', 'RU', 'PT', 'ZHS', 'ZHT'}


class Command(BaseCommand):
    help = 'Nettoie les donnees corrompues en BD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Affiche ce qui serait fait sans modifier la BD',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('[DRY RUN] Aucune modification ne sera appliquee\n'))

        total_changes = 0
        total_changes += self._fix_conditions(dry_run)
        total_changes += self._fix_languages(dry_run)
        total_changes += self._delete_invalid_prices(dry_run)
        total_changes += self._delete_bad_cards(dry_run)
        total_changes += self._deactivate_duplicate_stores(dry_run)

        self.stdout.write(f"\n{'='*60}")
        if dry_run:
            self.stdout.write(self.style.WARNING(f'{total_changes} modification(s) en attente (relancez sans --dry-run)'))
        else:
            self.stdout.write(self.style.SUCCESS(f'{total_changes} modification(s) appliquee(s)'))
        self.stdout.write(f"{'='*60}\n")

    def _fix_conditions(self, dry_run):
        self.stdout.write('\n--- Conditions ---')
        count = 0
        for old, new in CONDITION_MIGRATION.items():
            qs = CardPrice.objects.filter(condition=old)
            n = qs.count()
            if n == 0:
                continue
            self.stdout.write(f"  {repr(old):25s} -> {repr(new):8s} ({n} prix)")
            if not dry_run:
                qs.update(condition=new)
            count += n
        if count == 0:
            self.stdout.write('  Rien a migrer')
        return count

    def _fix_languages(self, dry_run):
        self.stdout.write('\n--- Langues ---')
        count = 0
        for old, new in LANGUAGE_MIGRATION.items():
            qs = CardPrice.objects.filter(language=old)
            n = qs.count()
            if n == 0:
                continue
            self.stdout.write(f"  {repr(old):25s} -> {repr(new):8s} ({n} prix)")
            if not dry_run:
                qs.update(language=new)
            count += n
        if count == 0:
            self.stdout.write('  Rien a migrer')
        return count

    def _delete_invalid_prices(self, dry_run):
        self.stdout.write('\n--- Prix avec condition ou langue invalide ---')
        # Exclut aussi les valeurs qui seront migrées (pour éviter faux positifs en dry-run)
        safe_conditions = VALID_CONDITIONS | set(CONDITION_MIGRATION.keys())
        safe_languages = VALID_LANGUAGES | set(LANGUAGE_MIGRATION.keys())
        invalid_cond = CardPrice.objects.exclude(condition__in=safe_conditions)
        invalid_lang = CardPrice.objects.exclude(language__in=safe_languages)

        to_delete = (invalid_cond | invalid_lang).distinct()
        count = to_delete.count()

        if count == 0:
            self.stdout.write('  Aucun')
            return 0

        for p in to_delete:
            self.stdout.write(
                self.style.ERROR(
                    f"  [SUPPR] {p.card.name} | condition={repr(p.condition)} "
                    f"| langue={repr(p.language)} | {p.price}$"
                )
            )

        if not dry_run:
            to_delete.delete()

        return count

    def _delete_bad_cards(self, dry_run):
        self.stdout.write('\n--- Cartes avec scryfall_id vide ---')
        bad_cards = Card.objects.filter(scryfall_id='')
        count = bad_cards.count()

        if count == 0:
            self.stdout.write('  Aucune')
            return 0

        total = 0
        for card in bad_cards:
            prices_count = card.prices.count()
            self.stdout.write(
                self.style.ERROR(
                    f"  [SUPPR] [{card.id}] {card.name} ({card.set_code} #{card.collector_number})"
                    f" + {prices_count} prix"
                )
            )
            total += 1 + prices_count

        if not dry_run:
            # Les prix sont supprimés en cascade (on_delete=CASCADE)
            bad_cards.delete()

        return total

    def _deactivate_duplicate_stores(self, dry_run):
        self.stdout.write('\n--- Stores en doublon ---')
        # "Face to Face" est un doublon de "Face to Face Games"
        duplicates = Store.objects.filter(name='Face to Face', is_active=True, prices=None)
        count = duplicates.count()

        if count == 0:
            self.stdout.write('  Aucun')
            return 0

        for store in duplicates:
            self.stdout.write(
                self.style.WARNING(f"  [DESACTIVER] [{store.id}] {repr(store.name)}")
            )

        if not dry_run:
            duplicates.update(is_active=False)

        return count
