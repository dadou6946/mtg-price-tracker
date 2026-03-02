"""
Classe de base pour les scrapers de sites Crystal Commerce.

Crystal Commerce est une plateforme e-commerce utilisée par plusieurs boutiques MTG.
Structure HTML commune :
  <li class="product">
    <div class="variant-row in-stock">
      <span class="variant-short-info variant-qty">N En stock</span>
      <form class="add-to-cart-form"
            data-vid="..."
            data-name="Card Name - Foil - Variant"
            data-price="CAD$ X.XX"
            data-variant="NM-Mint, English[, ...]"
            data-category="Set Name">

Les formulaires sont répétés 3× (grille/liste/détail) → dédup par data-vid.
Le site n'expose pas le numéro de collection.
"""
import time
import requests
import re
from decimal import Decimal
from abc import abstractmethod

from bs4 import BeautifulSoup

from scrapers.base import BaseScraper


class BaseCrystalCommerceScraper(BaseScraper):

    CONDITION_MAP = {
        'NM-Mint':           'NM',
        'Nm-Mint':           'NM',   # variante de casse (L'Expédition)
        'Near Mint':         'NM',
        'Mint/Near-Mint':    'NM',   # Topdeck Hero
        'Brand New':         'NM',   # Topdeck Hero
        'NM':                'NM',   # forme déjà normalisée (certains stores)
        'Lightly Played':    'LP',
        'Light Play':        'LP',
        'Slightly Played':   'LP',
        'LP':                'LP',
        'Moderately Played': 'MP',
        'Moderatly Played':  'MP',   # faute de frappe (Topdeck Hero)
        'Moderate Play':     'MP',
        'MP':                'MP',
        'Heavily Played':    'HP',
        'Heavy Play':        'HP',
        'HP':                'HP',
        'Damaged':           'DMG',
        'DMG':               'DMG',
    }

    LANGUAGE_MAP = {
        'English':             'EN',
        'French':              'FR',
        'Japanese':            'JP',
        'German':              'DE',
        'Spanish':             'ES',
        'Italian':             'IT',
        'Korean':              'KO',
        'Russian':             'RU',
        'Portuguese':          'PT',
        'Francais':            'FR',   # sans accent (L'Expédition)
        'Chinese Simplified':  'ZHS',
        'Chinese Traditional': 'ZHT',
        'S-Chinese':           'ZHS',
        'T-Chinese':           'ZHT',
        'Phyrexian':           'PHY',
    }

    # Limite de pages : Crystal Commerce retourne parfois des centaines de pages
    # pour une recherche large. Au-delà de MAX_PAGES les résultats sont hors sujet.
    MAX_PAGES = 10

    # Mettre à False si le certificat SSL du site échoue la vérification Python (Windows).
    SSL_VERIFY = True

    def __init__(self):
        self.session = requests.Session()
        self.session.verify = self.SSL_VERIFY
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })

    @abstractmethod
    def _search_params(self, card_name: str, page: int) -> dict:
        """Retourne les paramètres de requête pour la page donnée."""
        raise NotImplementedError

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur le site et retourne les variantes en stock."""
        all_variants = []
        seen_vids = set()
        page = 1

        while page <= self.MAX_PAGES:
            params = self._search_params(card_name, page)
            try:
                response = self.session.get(self.SEARCH_URL, params=params, timeout=15)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"  [ERREUR RESEAU] {e}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            products = soup.select('li.product')

            if not products:
                break

            print(f"  Page {page}: {len(products)} produit(s)")

            for product in products:
                all_variants.extend(self._parse_product(product, seen_vids))

            page += 1
            if page <= self.MAX_PAGES:
                time.sleep(1)

        print(f"  {len(all_variants)} variante(s) en stock trouvee(s)")

        if set_code:
            all_variants = [v for v in all_variants if v.get('set_code') == set_code]
            print(f"  {len(all_variants)} variante(s) pour {set_code}")

        return all_variants

    def _parse_product(self, product_li, seen_vids):
        """Parse un produit Crystal Commerce et retourne ses variantes en stock."""
        variants_list = []

        link = product_li.select_one('a[href*="/catalog/"]')
        product_url = self.BASE_URL + link['href'] if link else self.BASE_URL

        for form in product_li.select('form.add-to-cart-form'):
            vid = form.get('data-vid')
            if not vid or vid in seen_vids:
                continue
            seen_vids.add(vid)

            data_name = form.get('data-name', '')
            data_variant = form.get('data-variant', '')
            data_price = form.get('data-price', '')
            data_category = form.get('data-category', '')

            if not data_name or not data_variant:
                continue

            # Foil : présence du mot "Foil" dans le nom du produit
            is_foil = bool(re.search(r'\bFoil\b', data_name, re.IGNORECASE))

            # Nom de la carte : supprimer les suffixes variant après " - "
            # (?:\d+\s*-\s*)? gère les noms du style "Card - 435 - Borderless ..." (Topdeck Hero)
            card_name = re.sub(
                r'\s*-\s*(?:\d+\s*-\s*)?(Foil|Showcase|Borderless|Extended Art|Retro Frame|Etched|'
                r'Textured|Galaxy Foil|Surge Foil|Full Art|Alternate Art|Promo|'
                r'Concept Praetor|Step-and-Compleat Foil|The List|Phyrexian|'
                r'Promo Pack|Prerelease Promo).*$',
                '', data_name, flags=re.IGNORECASE
            ).strip()

            # Condition et langue : "NM-Mint, English[, ------]" — on prend les 2 premiers
            variant_parts = [p.strip() for p in data_variant.split(',')]
            condition_raw = variant_parts[0]
            language_raw = variant_parts[1] if len(variant_parts) >= 2 else 'English'

            condition = self.CONDITION_MAP.get(condition_raw)
            language = self.LANGUAGE_MAP.get(language_raw)

            if condition is None:
                print(f"  [SKIP] Condition inconnue: {condition_raw!r} (vid: {vid})")
                continue
            if language is None:
                print(f"  [SKIP] Langue inconnue: {language_raw!r} (vid: {vid})")
                continue

            # Prix : "CAD$ 2.00"
            price_match = re.search(r'[\d]+\.?\d*', data_price.replace(',', ''))
            if not price_match:
                continue
            price = Decimal(price_match.group())

            # Stock : classe CSS du div.variant-row parent
            variant_row = form.find_parent('div', class_='variant-row')
            if variant_row:
                row_classes = variant_row.get('class', [])
                in_stock = 'in-stock' in row_classes
                qty_el = variant_row.select_one('.variant-short-info.variant-qty')
                if qty_el:
                    qty_match = re.search(r'\d+', qty_el.get_text())
                    quantity = int(qty_match.group()) if qty_match else None
                else:
                    quantity = None
            else:
                in_stock = True
                quantity = None

            set_code = self._resolve_set_code(data_category)

            variants_list.append({
                'name': card_name,
                'set_code': set_code,
                'collector_number': None,   # non disponible sur Crystal Commerce
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': language,
                'in_stock': in_stock,
                'stock_quantity': quantity,
                'url': product_url,
                'sku': vid,
            })

        return variants_list

    def _resolve_set_code(self, set_name):
        """Trouve le code de set depuis son nom complet via la base de données."""
        if not set_name:
            return None
        try:
            from cards.models import Card
            card = Card.objects.filter(set_name__iexact=set_name).first()
            if card:
                return card.set_code
        except Exception:
            pass
        return None

    def save_prices(self, card, store):
        """
        Recherche par nom+set et sauvegarde sans filtrer par collector_number.

        Crystal Commerce n'expose pas le numéro de collection.
        Tous les prix correspondant au nom + set de la carte sont sauvegardés.
        """
        from django.utils import timezone
        from cards.models import CardPrice

        products = self.search_card(card.name, card.set_code)

        if not products:
            return 0, 0

        products = [
            p for p in products
            if p['name'].lower() == card.name.lower()
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
