from scrapers.crystal_commerce import BaseCrystalCommerceScraper


class ExpeditionScraper(BaseCrystalCommerceScraper):
    """Scraper pour L'Expédition (expeditionjeux.com)

    Crystal Commerce — paramètre c=1 requis, même structure que Le Valet de Coeur.
    URL de recherche : https://www.expeditionjeux.com/products/search?q=...&c=1&page=N

    Particularités :
    - data-variant a 3 champs : "NM-Mint, English, Montréal" (3e = succursale, ignoré)
    - Deux succursales : Montréal et Rive-Sud (prix peuvent différer par succursale)
    - Produits non-MTG (Cardfight!! Vanguard) dans les résultats → skippés
      (condition "Nm-Mint" sans langue ou set_code=None après résolution)
    """

    STORE_NAME = "L'Expédition"

    BASE_URL = "https://www.expeditionjeux.com"
    SEARCH_URL = f"{BASE_URL}/products/search"

    def _search_params(self, card_name: str, page: int) -> dict:
        return {'q': card_name, 'c': 1, 'page': page}
