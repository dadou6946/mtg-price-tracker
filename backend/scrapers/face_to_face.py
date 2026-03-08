import requests
import re
import json
from decimal import Decimal

from scrapers.base import BaseScraper


class FaceToFaceScraper(BaseScraper):
    """Scraper pour Face to Face Games (facetofacegames.com)

    Extrait les données depuis la variable JavaScript 'var meta'
    présente dans la page de résultats de recherche.
    """

    STORE_NAME = "Face to Face Games"

    BASE_URL = "https://www.facetofacegames.com"
    SEARCH_URL = f"{BASE_URL}/fr/search"

    # Mappage codes Face to Face → codes modèle Django
    # Note: Face to Face utilise 'PL' pour Lightly Played, le modèle utilise 'LP'
    CONDITION_MAP = {
        'NM': 'NM',
        'PL': 'LP',
        'MP': 'MP',
        'HP': 'HP',
        'DMG': 'DMG',
    }

    LANGUAGE_MAP = {
        'ENG': 'EN',
        'FRE': 'FR',
        'GER': 'DE',
        'SPA': 'ES',
        'ITA': 'IT',
        'JPN': 'JP',
        'PHY': 'PHY',
        'KOR': 'KO',
        'RUS': 'RU',
        'POR': 'PT',
        'CHS': 'ZHS',
        'CHT': 'ZHT',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'
        })

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur Face to Face et retourne les variantes disponibles."""
        query = card_name.lower().replace(' ', '-')

        try:
            response = self.session.get(self.SEARCH_URL, params={'q': query}, timeout=10)
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
        """Parse un produit Face to Face et retourne ses variantes au format standard."""
        variants_list = []
        product_url = f"{self.BASE_URL}/fr/products/{product.get('handle', '')}"

        for variant in product.get('variants', []):
            sku = variant.get('sku', '')

            set_code = self._extract_set_code(sku)
            collector_number = self._extract_collector_number(sku)
            is_foil = self._is_foil(sku)

            condition = self.CONDITION_MAP.get(self._extract_condition_code(sku))
            if condition is None:
                print(f"  [SKIP] Condition inconnue dans SKU: {sku}")
                continue

            language = self.LANGUAGE_MAP.get(self._extract_language_code(sku))
            if language is None:
                print(f"  [SKIP] Langue inconnue dans SKU: {sku}")
                continue

            price = Decimal(variant.get('price', 0)) / 100

            raw_name = variant.get('name', '')
            card_name = re.sub(r'\s*-\s*(NM|PL|MP|HP|DMG)\s*$', '', raw_name)
            card_name = re.sub(r'\s*\[.*', '', card_name).strip()

            variants_list.append({
                'name': card_name,
                'collector_number': collector_number,
                'set_code': set_code,
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': language,
                'in_stock': True,
                'stock_quantity': 0,
                'url': product_url,
                'sku': sku,
            })

        return variants_list

    # --- Extracteurs de champs depuis le SKU ---
    # Ancien format : MTG-SINGLE-SET-COLLECTOR-LANG-CONDITION[-FOIL]
    #   ex: MTG-SINGLE-DMU-107-ENG-NM-F
    # Nouveau format : M-SET-CARDNAME-COLLECTOR-CONDITION-FOIL
    #   ex: M-KHM-Goldspan_D-139-NM-NF

    def _extract_set_code(self, sku):
        parts = sku.split('-')
        if parts[0] == 'M':
            return parts[1] if len(parts) > 1 else None
        return parts[2] if len(parts) > 2 else None

    def _extract_collector_number(self, sku):
        parts = sku.split('-')
        return parts[3] if len(parts) > 3 else None

    def _extract_language_code(self, sku):
        parts = sku.split('-')
        if parts[0] == 'M':
            return 'ENG'  # Nouveau format sans champ langue, EN par défaut
        return parts[4] if len(parts) > 4 else None

    def _extract_condition_code(self, sku):
        parts = sku.split('-')
        if parts[0] == 'M':
            return parts[4] if len(parts) > 4 else 'NM'
        return parts[5] if len(parts) > 5 else 'NM'

    def _is_foil(self, sku):
        parts = sku.split('-')
        if parts[0] == 'M':
            return len(parts) > 5 and parts[5] == 'F'
        return len(parts) > 6 and parts[6] in ('F', 'SF')


if __name__ == '__main__':
    scraper = FaceToFaceScraper()
    results = scraper.search_card("Fable of the Mirror-Breaker")

    if results:
        by_collector = {}
        for r in results:
            key = r['collector_number']
            by_collector.setdefault(key, []).append(r)

        for collector_num in sorted(by_collector.keys()):
            variants = by_collector[collector_num]
            first = variants[0]
            print(f"\n[{first['set_code']} #{collector_num}] {first['name']}")
            for v in variants:
                foil = "Foil" if v['foil'] else "Non-Foil"
                print(f"  {v['condition']:5s} {foil:10s} {v['price']:7.2f}$ CAD")
