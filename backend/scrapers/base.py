"""
Classe de base pour tous les scrapers de magasins MTG.

Pour ajouter un nouveau magasin :
  1. Créer scrapers/nom_magasin.py
  2. Créer une classe qui hérite de BaseScraper
  3. Définir STORE_NAME (doit correspondre au nom dans init_stores)
  4. Implémenter search_card() en retournant le format standardisé
  5. Ajouter la classe au SCRAPER_REGISTRY dans scrapers/__init__.py
"""

from abc import ABC, abstractmethod
from django.utils import timezone
from cards.models import CardPrice, Store


class BaseScraper(ABC):

    STORE_NAME = ""  # À définir dans chaque sous-classe

    @abstractmethod
    def search_card(self, card_name: str, set_code: str = None) -> list:
        """
        Recherche une carte sur le site du magasin.

        Retourne une liste de dicts avec les champs suivants :
          name           (str)      Nom de la carte
          set_code       (str)      Code du set (ex: DMU, NEO)
          collector_number (str)    Numéro de collectionneur
          price          (Decimal)  Prix
          currency       (str)      'CAD', 'USD', etc.
          condition      (str)      'NM', 'LP', 'MP', 'HP', 'DMG'
          foil           (bool)
          language       (str)      'EN', 'FR', 'JP', 'PHY', etc.
          in_stock       (bool)
          stock_quantity (int|None)
          url            (str)      URL du produit sur le site
        """
        raise NotImplementedError

    def get_store(self) -> Store:
        """Retourne l'objet Store correspondant à ce scraper."""
        try:
            return Store.objects.get(name=self.STORE_NAME)
        except Store.DoesNotExist:
            raise ValueError(
                f"Magasin '{self.STORE_NAME}' introuvable en BD. "
                f"Lancez 'python manage.py init_stores' d'abord."
            )

    def save_prices(self, card, store) -> tuple[int, int]:
        """
        Scrape et sauvegarde les prix d'une carte pour ce magasin.

        Retourne (nb_crees, nb_mis_a_jour).
        """
        products = self.search_card(card.name, card.set_code)

        if not products:
            return 0, 0

        if card.collector_number:
            products = [
                p for p in products
                if p.get('collector_number') == card.collector_number
            ]

        created = 0
        updated = 0
        for product in products:
            _, was_created = CardPrice.objects.update_or_create(
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
            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated
