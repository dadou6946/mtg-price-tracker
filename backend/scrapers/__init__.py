from scrapers.face_to_face import FaceToFaceScraper
from scrapers.le_coin_du_jeu import LeCoinDuJeuScraper
from scrapers.le_valet_de_coeur import LeValetDeCoeurScraper
from scrapers.goblin_argent import GoblinArgentScraper
from scrapers.secret_des_korrigans import SecretDesKorrigansScraper
from scrapers.expedition import ExpeditionScraper
from scrapers.topdeck_hero import TopdeckHeroScraper
from scrapers.altf4 import AltF4Scraper
from scrapers.three_dragons import ThreeDragonsScraper
from scrapers.remi_card_trader import RemiCardTraderScraper
from scrapers.mythic_store import MythicStoreScraper
from scrapers.multizone import MultizoneScraper

# Registre des scrapers actifs.
# Clé = nom du magasin (doit correspondre exactement au Store.name en BD).
# Pour ajouter un store : importer la classe et l'ajouter ici.
SCRAPER_REGISTRY = {
    "Face to Face Games": FaceToFaceScraper,
    "Le Coin du Jeu": LeCoinDuJeuScraper,
    "Le Valet de Coeur": LeValetDeCoeurScraper,
    "Le Goblin d'Argent": GoblinArgentScraper,
    "Le Secret des Korrigans": SecretDesKorrigansScraper,
    "L'Expédition": ExpeditionScraper,
    "Topdeck Hero": TopdeckHeroScraper,
    "Alt F4": AltF4Scraper,
    "3 Dragons": ThreeDragonsScraper,
    "Rémi Card Trader": RemiCardTraderScraper,
    "The Mythic Store": MythicStoreScraper,
    "Multizone": MultizoneScraper,
}
