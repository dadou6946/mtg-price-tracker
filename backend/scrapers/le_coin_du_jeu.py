import requests
import re
import json
from decimal import Decimal

from scrapers.base import BaseScraper


class LeCoinDuJeuScraper(BaseScraper):
    """Scraper pour Le Coin du Jeu (lecoindujeu.ca)

    Shopify — même structure 'var meta' que Face to Face.

    SKU format standard (5 parts) : SET-COLLECTOR-LANG-FOIL-CONDITION_NUM
      Exemple : DMU-107-EN-NF-1
        parts[0] = set_code       (DMU)
        parts[1] = collector_num  (107)
        parts[2] = langue         (EN)
        parts[3] = foil           (NF = Non-Foil, FO = Foil)
        parts[4] = condition num  (1=NM, 2=LP, 3=MP, 4=HP, 5=DMG)

    Les SKUs de promos ont des formats variables (6-7 parts).
    On utilise public_title pour condition + foil sur tous les formats.
    """

    STORE_NAME = "Le Coin du Jeu"

    BASE_URL = "https://www.lecoindujeu.ca"
    SEARCH_URL = f"{BASE_URL}/search"

    # Mappage public_title → (condition_code, is_foil)
    # "Slightly Played" est un alias de "Lightly Played" utilisé sur certains produits
    PUBLIC_TITLE_MAP = {
        'Near Mint':                ('NM',  False),
        'Lightly Played':           ('LP',  False),
        'Slightly Played':          ('LP',  False),
        'Moderately Played':        ('MP',  False),
        'Heavily Played':           ('HP',  False),
        'Damaged':                  ('DMG', False),
        'Near Mint Foil':           ('NM',  True),
        'Lightly Played Foil':      ('LP',  True),
        'Slightly Played Foil':     ('LP',  True),
        'Moderately Played Foil':   ('MP',  True),
        'Heavily Played Foil':      ('HP',  True),
        'Damaged Foil':             ('DMG', True),
        'Foil / Near Mint':         ('NM',  True),
        'Foil / Slightly Played':   ('LP',  True),
        'Foil / Moderately Played': ('MP',  True),
        'Foil / Heavily Played':    ('HP',  True),
        'Foil / Damaged':           ('DMG', True),
    }

    # Codes langue reconnus (cherchés dans les segments du SKU)
    LANGUAGE_CODES = {'EN', 'FR', 'JP', 'DE', 'ES', 'IT', 'KO', 'PHY', 'RU', 'PT', 'ZHS', 'ZHT'}

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'
        })

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur Le Coin du Jeu et retourne les variantes disponibles."""
        try:
            response = self.session.get(
                self.SEARCH_URL,
                params={'q': card_name},
                timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as e:
            print(f"  [ERREUR RESEAU] {e}")
            return []

        products_data = self._extract_meta_products(response.text)
        if not products_data:
            return []

        all_variants = []
        for product in products_data:
            all_variants.extend(self._parse_product(product))

        print(f"  {len(all_variants)} variante(s) trouvee(s)")

        if set_code:
            all_variants = [v for v in all_variants if v.get('set_code') == set_code]
            print(f"  {len(all_variants)} variante(s) pour {set_code}")

        return all_variants

    def _extract_meta_products(self, html):
        """Extrait la liste de produits depuis 'var meta = {...}'."""
        match = re.search(r'var meta\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not match:
            print("  [WARN] 'var meta' introuvable dans la page")
            return []

        try:
            meta = json.loads(match.group(1))
            products = meta.get('products', [])
            print(f"  {len(products)} produit(s) dans var meta")
            return products
        except json.JSONDecodeError as e:
            print(f"  [ERREUR JSON] {e}")
            return []

    def _parse_product(self, product):
        """Parse un produit LCdJ et retourne ses variantes au format standard."""
        variants_list = []
        handle = product.get('handle', '')
        product_url = f"{self.BASE_URL}/products/{handle}"

        for variant in product.get('variants', []):
            sku = variant.get('sku', '')
            public_title = variant.get('public_title', '')

            # Condition et foil depuis public_title (fiable pour tous les formats de SKU)
            parsed = self.PUBLIC_TITLE_MAP.get(public_title)
            if parsed is None:
                print(f"  [SKIP] public_title inconnu: {public_title!r} (SKU: {sku})")
                continue
            condition, is_foil = parsed

            # set_code et collector_number depuis les 2 premiers segments du SKU
            parts = sku.split('-')
            if len(parts) < 2:
                print(f"  [SKIP] SKU invalide: {sku!r}")
                continue

            set_code = parts[0]
            collector_number = parts[1]

            # Langue : cherche le premier code connu dans les segments du SKU
            language = next((p for p in parts if p in self.LANGUAGE_CODES), 'EN')

            price = Decimal(variant.get('price', 0)) / 100

            # Nettoyage du nom :
            # "Sheoldred, the Apocalypse (Showcase) [Dominaria United] - Near Mint"
            # → "Sheoldred, the Apocalypse"
            raw_name = variant.get('name', '')
            card_name = re.sub(
                r'\s*-\s*(Near Mint|Lightly Played|Slightly Played|Moderately Played|'
                r'Heavily Played|Damaged).*$',
                '', raw_name, flags=re.IGNORECASE
            )
            card_name = re.sub(r'\s*[\[(].*', '', card_name).strip()

            variants_list.append({
                'name': card_name,
                'set_code': set_code,
                'collector_number': collector_number,
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': language,
                'in_stock': True,    # non disponible dans var meta
                'stock_quantity': None,
                'url': product_url,
                'sku': sku,
            })

        return variants_list


if __name__ == '__main__':
    scraper = LeCoinDuJeuScraper()
    results = scraper.search_card("Sheoldred, the Apocalypse")

    if results:
        by_collector = {}
        for r in results:
            key = (r['set_code'], r['collector_number'])
            by_collector.setdefault(key, []).append(r)

        for (set_code, num) in sorted(by_collector.keys()):
            variants = by_collector[(set_code, num)]
            first = variants[0]
            print(f"\n[{set_code} #{num}] {first['name']}")
            for v in variants:
                foil = "Foil" if v['foil'] else "Non-Foil"
                print(f"  {v['condition']:5s} {foil:10s} {v['price']:7.2f}$ CAD")
