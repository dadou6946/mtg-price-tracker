from scrapers.crystal_commerce import BaseCrystalCommerceScraper


class SecretDesKorrigansScraper(BaseCrystalCommerceScraper):
    """Scraper pour Le Secret des Korrigans (lesecretdeskorrigans.com)

    Crystal Commerce — même structure que Le Valet de Coeur.
    URL de recherche : https://www.lesecretdeskorrigans.com/products/search?q=...&page=N
    """

    STORE_NAME = "Le Secret des Korrigans"

    BASE_URL = "https://www.lesecretdeskorrigans.com"
    SEARCH_URL = f"{BASE_URL}/products/search"

    def _search_params(self, card_name: str, page: int) -> dict:
        return {'q': card_name, 'page': page}


if __name__ == '__main__':
    import django
    import os
    import sys
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    sys.path.insert(0, '.')
    django.setup()

    scraper = SecretDesKorrigansScraper()
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
