"""
Scraper pour 3 Dragons (3dragons.ca)

Shopify — var meta dans la page HTML.

SKU format : SET-COLLECTOR-CONDITION-FOIL
  Exemple   : DMU-107-NM-N
    parts[0] = set_code        (DMU)
    parts[1] = collector_num   (107, 107p, 107s, ...)
    parts[2] = condition       (NM, SP, MP, HP, DMG)
    parts[3] = foil            (N = Regular, F = Foil)

public_title : "NM / Regular" ou "NM / Foil"
  - None → produit non-carte (accessoire, binder...) → ignoré
  - Part 0 = condition, Part 1 = foil type

Particularités :
  - Pas de champ langue → défaut 'EN' (magasin principalement anglais)
  - Cartes DFC affichées "Card // Card [SET-COLLECTOR]" → on prend avant "//"
  - price = 0 → listing placeholder → ignoré
  - Handle = UUID → URL /fr/products/{uuid}
  - SP (Slightly Played) → normalisé en LP
  - La recherche Shopify fonctionne bien sur ce site
"""
import re
import json
import time
import requests
from decimal import Decimal

from scrapers.base import BaseScraper


class ThreeDragonsScraper(BaseScraper):

    STORE_NAME = "3 Dragons"

    BASE_URL = "https://www.3dragons.ca"
    SEARCH_URL = f"{BASE_URL}/fr/search"

    MAX_PAGES = 5

    CONDITION_MAP = {
        'NM':  'NM',
        'SP':  'LP',   # Slightly Played
        'MP':  'MP',
        'HP':  'HP',
        'DMG': 'DMG',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur 3 Dragons et retourne les variantes disponibles."""
        all_variants = []
        page = 1

        while page <= self.MAX_PAGES:
            params = {
                'q': card_name,
                'type': 'product,',
                'options[prefix]': 'last',
                'filter.p.product_type': 'MTG Singles',
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
        """Parse un produit 3 Dragons et retourne ses variantes au format standard."""
        variants_list = []
        handle = product.get('handle', '')
        product_url = f"{self.BASE_URL}/fr/products/{handle}"

        for variant in product.get('variants', []):
            sku = variant.get('sku', '')
            public_title = variant.get('public_title')

            # public_title=None → accessoire ou produit non-carte
            if public_title is None:
                continue

            # SKU format : SET-COLLECTOR-CONDITION-FOIL (toujours 4 parties)
            parts = sku.split('-')
            if len(parts) < 4:
                print(f"  [SKIP] SKU invalide: {sku!r}")
                continue

            set_code = parts[0]
            collector_number = parts[1]
            condition_raw = parts[2]
            foil_raw = parts[3]

            condition = self.CONDITION_MAP.get(condition_raw)
            if condition is None:
                print(f"  [SKIP] Condition inconnue: {condition_raw!r} (SKU: {sku})")
                continue

            is_foil = foil_raw == 'F'

            price = Decimal(variant.get('price', 0)) / 100
            if price == 0:
                continue   # listing placeholder sans prix

            # Nom de la carte :
            # "Sheoldred, the Apocalypse // Sheoldred, the Apocalypse [ADMU-26] - NM / Regular"
            # "Sheoldred, the Apocalypse - Showcase [DMU-369] - NM / Regular"
            raw_name = variant.get('name', '')
            # 1) DFC : prendre avant " // "
            if ' // ' in raw_name:
                raw_name = raw_name.split(' // ')[0]
            # 2) Supprimer " [SET-COLLECTOR] - ..." et tout ce qui suit
            card_name = re.sub(r'\s*[\[(].*', '', raw_name).strip()
            # 3) Supprimer les suffixes variant " - Showcase", " - Borderless", etc.
            card_name = re.sub(
                r'\s*-\s*(Showcase|Borderless|Textured Foil|Concept Praetor|'
                r'Compleat Foil|Full Art|Extended Art|Promo Pack|Prerelease Promo|'
                r'Etched Foil|Galaxy Foil|Surge Foil|Alternate Art|Retro Frame).*$',
                '', card_name, flags=re.IGNORECASE
            ).strip()

            variants_list.append({
                'name': card_name,
                'set_code': set_code,
                'collector_number': collector_number,
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': 'EN',       # pas de champ langue sur ce site
                'in_stock': True,       # available=None systématiquement
                'stock_quantity': None,
                'url': product_url,
                'sku': sku,
            })

        return variants_list
