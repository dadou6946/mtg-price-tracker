from scrapers.crystal_commerce import BaseCrystalCommerceScraper


class LeValetDeCoeurScraper(BaseCrystalCommerceScraper):
    """Scraper pour Le Valet de Coeur (carte.levalet.com)

    Crystal Commerce — paramètre c=1 requis pour filtrer les cartes MTG.
    URL de recherche : https://carte.levalet.com/products/search?q=...&c=1&page=N
    """

    STORE_NAME = "Le Valet de Coeur"

    BASE_URL = "https://carte.levalet.com"
    SEARCH_URL = f"{BASE_URL}/products/search"

    def _search_params(self, card_name: str, page: int) -> dict:
        return {'q': card_name, 'c': 1, 'page': page}


if __name__ == '__main__':
    import django
    import os
    import sys
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    sys.path.insert(0, '.')
    django.setup()

    scraper = LeValetDeCoeurScraper()
    results = scraper.search_card("Sheoldred, the Apocalypse")

    if results:
        by_product = {}
        for r in results:
            key = (r['set_code'] or r['sku'], r['name'], r['foil'])
            by_product.setdefault(key, []).append(r)

        for (set_code, name, foil), variants in sorted(by_product.items()):
            foil_str = "Foil" if foil else "Non-Foil"
            print(f"\n[{set_code}] {name} ({foil_str})")
            for v in variants:
                stock = f"{v['stock_quantity']}x" if v['stock_quantity'] else ('En stock' if v['in_stock'] else 'OOS')
                print(f"  {v['condition']:5s} {v['language']:4s} {v['price']:7.2f}$ CAD  {stock}")
