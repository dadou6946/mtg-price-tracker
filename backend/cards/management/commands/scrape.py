import time

from django.core.management.base import BaseCommand
from cards.models import Card, Store
from scrapers import SCRAPER_REGISTRY


class Command(BaseCommand):
    help = 'Scrape les prix depuis les magasins enregistres'

    def add_arguments(self, parser):
        parser.add_argument(
            '--store',
            type=str,
            help='Nom du magasin a scraper (defaut: tous les magasins enregistres)',
        )
        parser.add_argument(
            '--card-name',
            type=str,
            help='Rechercher une carte par nom sur le site',
        )
        parser.add_argument(
            '--set',
            type=str,
            help='Filtrer par code de set (ex: DMU, NEO)',
        )
        parser.add_argument(
            '--all-versions',
            action='store_true',
            help='Sauvegarder toutes les versions trouvees (defaut: premiere version seulement)',
        )

    def handle(self, *args, **options):
        scrapers = self._get_scrapers(options.get('store'))
        if not scrapers:
            return

        card_name = options.get('card_name')

        for store_name, scraper_class in scrapers.items():
            scraper = scraper_class()

            try:
                store = scraper.get_store()
            except ValueError as e:
                self.stdout.write(self.style.ERROR(str(e)))
                continue

            self.stdout.write(f"\n{'='*60}")
            self.stdout.write(f"Magasin : {store_name}")
            self.stdout.write(f"{'='*60}")

            if card_name:
                self._scrape_by_name(scraper, store, options)
            else:
                self._scrape_all_tracked(scraper, store)

    # ------------------------------------------------------------------
    # Mode 1 : recherche par nom sur le site
    # ------------------------------------------------------------------

    def _scrape_by_name(self, scraper, store, options):
        from cards.models import CardPrice
        from django.utils import timezone

        card_name = options['card_name']
        set_code = options.get('set')
        all_versions = options.get('all_versions', False)

        self.stdout.write(f"Recherche : {card_name}\n")

        products = scraper.search_card(card_name, set_code)
        if not products:
            self.stdout.write(self.style.WARNING("Aucun produit trouve"))
            return

        # Groupe par (set_code, collector_number) puis par nom
        # Quand collector_number est None (ex: Le Valet), on regroupe par (set, nom)
        versions = {}
        for p in products:
            if p['collector_number']:
                key = (p['set_code'], p['collector_number'], None)
            else:
                key = (p['set_code'], None, p['name'].lower())
            versions.setdefault(key, []).append(p)

        self.stdout.write(f"{len(products)} produit(s) | {len(versions)} version(s)\n")

        total_created = 0
        total_updated = 0
        not_in_db = []
        saved_versions = 0

        for (set_found, collector_num, name_key), version_products in versions.items():
            if not set_found:
                continue

            if collector_num:
                # Numéro de collection connu : match exact
                try:
                    db_cards = [Card.objects.get(set_code=set_found, collector_number=collector_num)]
                except Card.DoesNotExist:
                    not_in_db.append(f"{set_found} #{collector_num} ({version_products[0]['name']})")
                    continue
            else:
                # Pas de numéro de collection : match par nom + set
                product_name = version_products[0]['name']
                db_cards = list(Card.objects.filter(set_code=set_found, name__iexact=product_name))
                if not db_cards:
                    not_in_db.append(f"{set_found} {product_name!r} (sans num. collection)")
                    continue

            for card in db_cards:
                self.stdout.write(f"[{set_found} #{card.collector_number}] {card.name}")
                for product in version_products:
                    _, created = CardPrice.objects.update_or_create(
                        card=card,
                        store=store,
                        condition=product['condition'],
                        foil=product['foil'],
                        language=product['language'],
                        defaults={
                            'price': product['price'],
                            'currency': product['currency'],
                            'in_stock': product['in_stock'],
                            'quantity': product['stock_quantity'],
                            'url': product['url'],
                            'scraped_at': timezone.now(),
                        }
                    )
                    action = "[NEW]" if created else "[MAJ]"
                    foil = "Foil" if product['foil'] else "Non-Foil"
                    self.stdout.write(
                        f"  {action} {product['condition']:5s} {foil:10s} {product['price']:6.2f}$"
                    )
                    if created:
                        total_created += 1
                    else:
                        total_updated += 1

            saved_versions += 1
            if not all_versions:
                break

        self.stdout.write(f"\nCrees : {total_created} | Mis a jour : {total_updated}")

        if not_in_db:
            self.stdout.write(self.style.WARNING(
                f"\n{len(not_in_db)} version(s) sur le site absente(s) de la BD :"
            ))
            for entry in not_in_db:
                self.stdout.write(f"  - {entry}")
            self.stdout.write("  -> Utilisez 'add_card_versions' ou 'import_cards' pour les ajouter.")

    # ------------------------------------------------------------------
    # Mode 2 : scrape toutes les cartes suivies
    # ------------------------------------------------------------------

    def _scrape_all_tracked(self, scraper, store):
        cards = Card.objects.filter(is_tracked=True)
        total = cards.count()

        if total == 0:
            self.stdout.write(self.style.WARNING("Aucune carte suivie en BD"))
            return

        self.stdout.write(f"{total} carte(s) a scraper\n")

        total_created = 0
        total_updated = 0
        errors = 0

        for i, card in enumerate(cards, 1):
            self.stdout.write(f"[{i}/{total}] {card.name} ({card.set_code} #{card.collector_number})")
            try:
                created, updated = scraper.save_prices(card, store)
                total_created += created
                total_updated += updated
                self.stdout.write(
                    f"  -> {created} nouveau(x), {updated} mis a jour"
                )
            except Exception as e:
                errors += 1
                self.stdout.write(self.style.ERROR(f"  -> Erreur : {e}"))

            if i < total:
                time.sleep(1.5)  # Politesse envers le serveur

        self.stdout.write(f"\nTermine : {total_created} crees, {total_updated} mis a jour, {errors} erreur(s)")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_scrapers(self, store_name):
        if store_name:
            if store_name not in SCRAPER_REGISTRY:
                available = ", ".join(SCRAPER_REGISTRY.keys())
                self.stdout.write(self.style.ERROR(
                    f"Magasin '{store_name}' non trouve dans le registre.\n"
                    f"Disponibles : {available}"
                ))
                return {}
            return {store_name: SCRAPER_REGISTRY[store_name]}

        if not SCRAPER_REGISTRY:
            self.stdout.write(self.style.ERROR("Aucun scraper enregistre dans SCRAPER_REGISTRY"))
            return {}

        return SCRAPER_REGISTRY
