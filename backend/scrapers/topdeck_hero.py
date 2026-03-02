from scrapers.crystal_commerce import BaseCrystalCommerceScraper


class TopdeckHeroScraper(BaseCrystalCommerceScraper):
    """Scraper pour Topdeck Hero (topdeckhero.com)

    Crystal Commerce — même structure que Le Secret des Korrigans.
    URL de recherche : https://www.topdeckhero.com/products/search?q=...&page=N

    Particularités :
    - data-variant : "Mint/Near-Mint, English" (condition NM sous forme différente)
    - "Hero Deal" comme condition → ignoré (deal spécial du magasin, pas une condition MTG)
    """

    STORE_NAME = "Topdeck Hero"

    BASE_URL = "https://www.topdeckhero.com"
    SSL_VERIFY = False   # certificat SSL non reconnu par Python sur Windows
    SEARCH_URL = f"{BASE_URL}/products/search"

    def _search_params(self, card_name: str, page: int) -> dict:
        return {'q': card_name, 'page': page}
