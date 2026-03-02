"""
Scraper pour Multizone (multizone.ca)

Shopify — var meta dans la page HTML.

SKU format : SET-COLLECTOR-[EXTRA-]LANG-FOIL-COND_NUM
  Standard   : DMU-290-EN-NF-1      (5 parties)
  Promo Pack : PDMU-107-PROMO-PACK-EN-NF-1  (7 parties)

  Extraction robuste (identique à Rémi Card Trader) :
    parts[0]  = set_code
    parts[1]  = collector_number
    parts[-3] = code langue (EN, FR, JP, ...)
    parts[-2] = foil        (NF = Non-Foil, FO = Foil)
    parts[-1] = condition   (1=NM, 2=SP, 3=MP, 4=HP, 5=DMG)

public_title : "Near Mint", "Slightly Played Foil", ...
  → condition + foil en un seul champ (pas de séparateur "/")
  → "Slightly Played" (SP) normalisé en LP

name format : "Card Name (variant) [SET NAME] - Condition"

Particularités :
  - Recherche avec wildcards : q=*Card Name*
  - available = None systématiquement → in_stock=True
  - Dédup par product id (Shopify répète la p.1 sur pages suivantes)
"""
import re
import json
import time
import requests
from decimal import Decimal

from scrapers.base import BaseScraper


class MultizoneScraper(BaseScraper):

    STORE_NAME = "Multizone"

    BASE_URL = "https://multizone.ca"
    SEARCH_URL = f"{BASE_URL}/search"

    MAX_PAGES = 5

    PUBLIC_TITLE_MAP = {
        'Near Mint':                ('NM',  False),
        'Slightly Played':          ('LP',  False),
        'Moderately Played':        ('MP',  False),
        'Heavily Played':           ('HP',  False),
        'Damaged':                  ('DMG', False),
        'Near Mint Foil':           ('NM',  True),
        'Slightly Played Foil':     ('LP',  True),
        'Moderately Played Foil':   ('MP',  True),
        'Heavily Played Foil':      ('HP',  True),
        'Damaged Foil':             ('DMG', True),
    }

    LANGUAGE_CODES = {'EN', 'FR', 'JP', 'DE', 'ES', 'IT', 'KO', 'PHY', 'RU', 'PT', 'ZHS', 'ZHT'}

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur Multizone et retourne les variantes disponibles."""
        all_variants = []
        seen_ids = set()
        page = 1

        while page <= self.MAX_PAGES:
            try:
                response = self.session.get(
                    self.SEARCH_URL,
                    params={'q': f'*{card_name}*', 'page': page},
                    timeout=15
                )
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"  [ERREUR RESEAU] {e}")
                break

            products = self._extract_meta_products(response.text)
            if not products:
                break

            new_products = [p for p in products if p.get('id') not in seen_ids]
            if not new_products:
                break

            print(f"  Page {page}: {len(new_products)} nouveau(x) produit(s)")
            for product in new_products:
                seen_ids.add(product.get('id'))
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
        """Parse un produit Multizone et retourne ses variantes au format standard."""
        variants_list = []
        handle = product.get('handle', '')
        product_url = f"{self.BASE_URL}/products/{handle}"

        for variant in product.get('variants', []):
            sku = variant.get('sku', '')
            public_title = variant.get('public_title', '')

            parsed = self.PUBLIC_TITLE_MAP.get(public_title)
            if parsed is None:
                print(f"  [SKIP] public_title inconnu: {public_title!r} (SKU: {sku})")
                continue
            condition, is_foil = parsed

            # set_code = parts[0], collector_number = parts[1]
            # langue = parts[-3] (robuste face aux SKU 5-7 parties)
            parts = sku.split('-')
            if len(parts) < 5:
                print(f"  [SKIP] SKU invalide: {sku!r}")
                continue

            set_code = parts[0]
            collector_number = parts[1]
            language = next((p for p in reversed(parts[2:-2]) if p in self.LANGUAGE_CODES), 'EN')

            price = Decimal(variant.get('price', 0)) / 100

            raw_name = variant.get('name', '')
            card_name = re.sub(r'\s*[\[(].*', '', raw_name).strip()

            variants_list.append({
                'name': card_name,
                'set_code': set_code,
                'collector_number': collector_number,
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': language,
                'in_stock': True,       # available=None systématiquement
                'stock_quantity': None,
                'url': product_url,
                'sku': sku,
            })

        return variants_list
