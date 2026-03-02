import requests
import re
import json
from decimal import Decimal

from scrapers.base import BaseScraper


class GoblinArgentScraper(BaseScraper):
    """Scraper pour Le Goblin d'Argent (silvergoblin.cards)

    Shopify — même structure 'var meta' que Face to Face et Le Coin du Jeu.

    SKU formats :
      Standard (5 parts) :  SET-COLLECTOR-LANG-FOIL-CONDITION_NUM
        ex: DMU-107-EN-NF-1
      Promo (6 parts) :     PSET-COLLECTOR-PROMO_TYPE-LANG-FOIL-CONDITION_NUM
        ex: PDMU-107-PRERELEASE-EN-FO-1
      Promo Pack (7 parts) : PSET-COLLECTOR-PROMO-PACK-LANG-FOIL-CONDITION_NUM
        ex: PDMU-107-PROMO-PACK-EN-NF-1
      Ancien Shopify (4-6 parts, préfixe MTG-) :
        ex: MTG-5ED-HQ63KJGVX0-1      (set seulement, pas de collector_number)
            MTG-MB2PC-270-IGPBRCGKHZ-1 (avec collector_number)
            MTG-M3C-371-F-LCIPHKMMUV-1 (avec foil flag)

    On utilise public_title pour condition + foil sur tous les formats de SKU.
    set_code = parts[0] (sauf si 'MTG', alors parts[1]).
    collector_number = parts[1] (sauf si 'MTG', alors parts[2] si numérique).
    """

    STORE_NAME = "Le Goblin d'Argent"

    BASE_URL = "https://silvergoblin.cards"
    SEARCH_URL = f"{BASE_URL}/fr/search"

    # Même mappage que Le Coin du Jeu
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

    # Codes langue reconnus dans les segments du SKU
    LANGUAGE_CODES = {'EN', 'FR', 'JP', 'DE', 'ES', 'IT', 'KO', 'PHY', 'RU', 'PT', 'ZHS', 'ZHT'}

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8',
        })

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur Le Goblin d'Argent et retourne les variantes disponibles."""
        try:
            response = self.session.get(
                self.SEARCH_URL,
                params={'q': card_name, 'options[prefix]': 'last'},
                timeout=10,
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
        """Parse un produit Goblin d'Argent et retourne ses variantes au format standard."""
        variants_list = []
        handle = product.get('handle', '')
        product_url = f"{self.BASE_URL}/fr/products/{handle}"

        for variant in product.get('variants', []):
            sku = variant.get('sku', '')
            public_title = variant.get('public_title', '')

            # Condition et foil depuis public_title
            parsed = self.PUBLIC_TITLE_MAP.get(public_title)
            if parsed is None:
                print(f"  [SKIP] public_title inconnu: {public_title!r} (SKU: {sku})")
                continue
            condition, is_foil = parsed

            # set_code et collector_number depuis le SKU
            set_code, collector_number = self._extract_set_and_collector(sku)
            if not set_code:
                print(f"  [SKIP] SKU invalide: {sku!r}")
                continue

            # Langue : premier code connu dans les segments du SKU
            parts = sku.split('-')
            language = next((p for p in parts if p in self.LANGUAGE_CODES), 'EN')

            price = Decimal(variant.get('price', 0)) / 100

            # Nettoyage du nom :
            # "Sheoldred, the Apocalypse (107) Foil - Dominaria United - Near Mint Foil"
            # → "Sheoldred, the Apocalypse"
            raw_name = variant.get('name', '')
            # Prend la partie avant le premier " - " (qui sépare nom/set/condition)
            card_name = raw_name.split(' - ')[0]
            # Supprime les groupes entre parenthèses : (107), (Showcase), (Foil), etc.
            card_name = re.sub(r'\s*\(.*?\)', '', card_name)
            # Supprime le suffixe " Foil" résiduel
            card_name = re.sub(r'\s+Foil\s*$', '', card_name, flags=re.IGNORECASE).strip()

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
                'sku': sku,
            })

        return variants_list

    def _extract_set_and_collector(self, sku):
        """
        Extrait (set_code, collector_number) depuis le SKU.

        Formats gérés :
          Standard    : SET-COLLECTOR-...      → ('SET', 'COLLECTOR')
          Ancien MTG  : MTG-SET-HASH-...       → ('SET', None)
          Ancien MTG+ : MTG-SET-COLLECTOR-...  → ('SET', 'COLLECTOR') si parts[2] est numérique
        """
        parts = sku.split('-')
        if len(parts) < 2:
            return None, None

        if parts[0] == 'MTG':
            set_code = parts[1] if len(parts) > 1 else None
            # parts[2] est un numéro de collection s'il est purement numérique
            raw = parts[2] if len(parts) > 2 else ''
            collector_number = raw if raw.isdigit() else None
        else:
            set_code = parts[0]
            collector_number = parts[1] if len(parts) > 1 else None

        return set_code, collector_number


if __name__ == '__main__':
    import django
    import os
    import sys
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    sys.path.insert(0, '.')
    django.setup()

    scraper = GoblinArgentScraper()
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
