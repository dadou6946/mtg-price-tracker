"""
Scraper pour Alt F4 (altf4online.com)

Shopify — var meta dans la page HTML.

Format du name : "Card Name (variant) [SET - COLLECTOR] - Condition / Language / Foil"
  - Set code et collector number extraits depuis les crochets [SET - COLLECTOR]
  - [HML - N/A] → collector_number = None (pas de numéro de collection)
  - [LIST - 131/038] → collector_number = "131/038" (format composite)

public_title : "Near Mint / English / Normal" → condition / langue / foil
  - Part 2 == "Foil" → foil=True, "Normal" → foil=False

Particularités :
  - SKU = numéro simple (inutilisable pour extraire set/collector)
  - available = None systématiquement → in_stock=True par défaut
  - Recherche Shopify peu fiable : la carte cible peut apparaître en page 5+
    → pagination jusqu'à MAX_PAGES pages avec délai entre pages
"""
import re
import json
import time
import requests
from decimal import Decimal

from scrapers.base import BaseScraper


class AltF4Scraper(BaseScraper):

    STORE_NAME = "Alt F4"

    BASE_URL = "https://altf4online.com"
    SEARCH_URL = f"{BASE_URL}/search"

    # Davantage de pages que Crystal Commerce car les résultats pertinents
    # peuvent apparaître en fin de liste sur ce site.
    MAX_PAGES = 15

    CONDITION_MAP = {
        'Near Mint':         'NM',
        'Lightly Played':    'LP',
        'Slightly Played':   'LP',
        'Moderately Played': 'MP',
        'Heavily Played':    'HP',
        'Damaged':           'DMG',
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
        'Chinese Simplified':  'ZHS',
        'Chinese Traditional': 'ZHT',
        'Phyrexian':           'PHY',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur Alt F4 en paginant à travers tous les résultats."""
        all_variants = []
        page = 1

        while page <= self.MAX_PAGES:
            params = {
                'q': card_name,
                'options[prefix]': 'last',
                'page': page,
            }
            try:
                response = self.session.get(self.SEARCH_URL, params=params, timeout=15)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"  [ERREUR RESEAU] {e}")
                break

            products = self._extract_meta_products(response.text)
            if not products:
                break

            print(f"  Page {page}: {len(products)} produit(s)")
            for product in products:
                all_variants.extend(self._parse_product(product))

            page += 1
            if page <= self.MAX_PAGES:
                time.sleep(1)

        print(f"  {len(all_variants)} variante(s) trouvee(s)")

        if set_code:
            all_variants = [v for v in all_variants if v.get('set_code') == set_code]
            print(f"  {len(all_variants)} variante(s) pour {set_code}")

        return all_variants

    def _extract_meta_products(self, html):
        """Extrait la liste de produits depuis 'var meta = {...}'."""
        match = re.search(r'var meta\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not match:
            return []
        try:
            meta = json.loads(match.group(1))
            return meta.get('products', [])
        except json.JSONDecodeError:
            return []

    def _parse_product(self, product):
        """Parse un produit Alt F4 et retourne ses variantes au format standard."""
        variants_list = []
        handle = product.get('handle', '')
        product_url = f"{self.BASE_URL}/products/{handle}"

        for variant in product.get('variants', []):
            name = variant.get('name', '')
            public_title = variant.get('public_title', '') or ''

            # Extraction set_code + collector_number depuis [SET - COLLECTOR]
            bracket_match = re.search(r'\[([A-Z0-9]+)\s*-\s*([^\]]+)\]', name)
            if not bracket_match:
                continue
            set_code = bracket_match.group(1)
            collector_raw = bracket_match.group(2).strip()
            collector_number = None if collector_raw.upper() == 'N/A' else collector_raw

            # Nom de la carte : tout avant le premier ( ou [
            card_name = re.sub(r'\s*[\[(].*', '', name).strip()

            # Condition / Langue / Foil depuis public_title
            pt_parts = [p.strip() for p in public_title.split('/')]
            if len(pt_parts) < 2:
                continue

            condition = self.CONDITION_MAP.get(pt_parts[0])
            if condition is None:
                print(f"  [SKIP] Condition inconnue: {pt_parts[0]!r}")
                continue

            language = self.LANGUAGE_MAP.get(pt_parts[1])
            if language is None:
                print(f"  [SKIP] Langue inconnue: {pt_parts[1]!r}")
                continue

            is_foil = len(pt_parts) > 2 and pt_parts[2].lower() == 'foil'

            price = Decimal(variant.get('price', 0)) / 100

            variants_list.append({
                'name': card_name,
                'set_code': set_code,
                'collector_number': collector_number,
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': language,
                'in_stock': True,       # non disponible dans var meta
                'stock_quantity': None,
                'url': product_url,
                'sku': variant.get('sku', ''),
            })

        return variants_list
