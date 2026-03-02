from django.core.management.base import BaseCommand
from cards.models import Store

class Command(BaseCommand):
    help = 'Initialise les magasins de Montréal'

    def handle(self, *args, **kwargs):
        stores_data = [
            {
                "name": "Face to Face Games",
                "url": "https://www.facetofacegames.com",
                "location": "Montréal, QC"
            },
            {
                "name": "Le Coin du Jeu",
                "url": "https://www.lecoindujeu.ca",
                "location": "Montréal, QC"
            },
            {
                "name": "L'Expédition",
                "url": "https://www.expeditionjeux.com",
                "location": "Montréal, QC",
                "is_active": False  # On commencera pas avec celui-ci
            },
            {
                "name": "Le Secret des Korrigans",
                "url": "https://www.lesecretdeskorrigans.com",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "Le Valet de Coeur",
                "url": "https://carte.levalet.com",
                "location": "Montréal, QC"
            },
            {
                "name": "Le Goblin d'Argent",
                "url": "https://silvergoblin.cards/fr",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "Alt F4",
                "url": "https://altf4online.com/fr",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "Topdeck Hero",
                "url": "https://www.topdeckhero.com",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "3 Dragons",
                "url": "https://www.3dragons.ca",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "Rémi Card Trader",
                "url": "https://singles.remicardtrader.ca",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "The Mythic Store",
                "url": "https://themythicstore.com",
                "location": "Montréal, QC",
                "is_active": False
            },
            {
                "name": "Multizone",
                "url": "https://multizone.ca",
                "location": "Montréal, QC",
                "is_active": False
            },
        ]

        for store_data in stores_data:
            store, created = Store.objects.get_or_create(
                name=store_data["name"],
                defaults=store_data
            )
            
            if created:
                self.stdout.write(
                    self.style.SUCCESS(f'[OK] {store.name} cree')
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f'[-] {store.name} existe deja')
                )

        self.stdout.write(
            self.style.SUCCESS('\nInitialisation terminee !')
        )