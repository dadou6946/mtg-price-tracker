"""
Scraper pour The Mythic Store (themythicstore.com)

Shopify — thème personnalisé, pas de var meta.
Structure HTML : div.productCard__card + li[data-variantid]

  data-producttype = "MTG Single" — filtre les non-cartes.
  data-producttags — JSON array de tags dont le nom du set (ex: "Dominaria United").
    → set_code extrait par essai successif des tags via DB (_resolve_set_code)

Variantes dans li[data-variantid] :
  data-varianttitle   : "Near Mint", "Near Mint Foil", "Lightly Played", ...
  data-variantprice   : prix en cents (ex: 14699 → 146.99 CAD)
  data-variantavailable : "true" / "false"
  data-variantqty     : quantité en stock

Particularités :
  - Pas de collector_number → save_prices() filtre par nom seulement
  - Pas de champ langue → défaut 'EN'
  - URL de recherche : /a/search?q=... (chemin non standard Shopify)
  - Pagination via &page=N (même principe que Shopify standard)
  - Dédup par data-productid (Shopify répète la p.1 quand plus de résultats)
  - _set_code_cache : évite les requêtes BD répétées pour les mêmes tags
"""
import re
import json
import time
import requests
from decimal import Decimal
from bs4 import BeautifulSoup

from scrapers.base import BaseScraper


class MythicStoreScraper(BaseScraper):

    STORE_NAME = "The Mythic Store"

    BASE_URL = "https://themythicstore.com"
    SEARCH_URL = f"{BASE_URL}/a/search"

    MAX_PAGES = 5

    VARIANT_TITLE_MAP = {
        'Near Mint':               ('NM',  False),
        'Lightly Played':          ('LP',  False),
        'Moderately Played':       ('MP',  False),
        'Heavily Played':          ('HP',  False),
        'Damaged':                 ('DMG', False),
        'Near Mint Foil':          ('NM',  True),
        'Lightly Played Foil':     ('LP',  True),
        'Moderately Played Foil':  ('MP',  True),
        'Heavily Played Foil':     ('HP',  True),
        'Damaged Foil':            ('DMG', True),
    }

    # Tags qui ne sont jamais des noms de set (couleurs, raretés, formats, types, etc.)
    NON_SET_TAGS = {
        'Black', 'White', 'Red', 'Green', 'Blue', 'Colorless', 'Gold', 'Multicolor',
        'Common', 'Uncommon', 'Rare', 'Mythic', 'Special', 'Bonus',
        'Standard', 'Pioneer', 'Modern', 'Legacy', 'Vintage', 'Pauper',
        'Commander', 'Explorer', 'Historic', 'Historicbrawl', 'Brawl',
        'Alchemy', 'Gladiator', 'Duel', 'Future', 'Unknown Event',
        'Foil', 'Normal', 'noPrice', 'Card',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept-Language': 'fr-CA,fr;q=0.9,en;q=0.8',
        })
        self._set_code_cache = {}

    def search_card(self, card_name, set_code=None):
        """Recherche une carte sur The Mythic Store et retourne les variantes."""
        all_variants = []
        seen_ids = set()
        page = 1

        while page <= self.MAX_PAGES:
            params = {'q': card_name, 'page': page}
            try:
                response = self.session.get(self.SEARCH_URL, params=params, timeout=15)
                response.raise_for_status()
            except requests.RequestException as e:
                print(f"  [ERREUR RESEAU] {e}")
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            cards = soup.select('div.productCard__card')

            if not cards:
                break

            new_cards = [c for c in cards if c.get('data-productid') not in seen_ids]
            if not new_cards:
                break

            print(f"  Page {page}: {len(new_cards)} produit(s)")
            for card in new_cards:
                seen_ids.add(card.get('data-productid'))
                all_variants.extend(self._parse_product(card))

            page += 1
            if page <= self.MAX_PAGES:
                time.sleep(1)

        print(f"  {len(all_variants)} variante(s) trouvee(s)")

        if set_code:
            all_variants = [v for v in all_variants if v.get('set_code') == set_code]
            print(f"  {len(all_variants)} variante(s) pour {set_code}")

        return all_variants

    def _parse_product(self, card_el):
        """Parse un produit Mythic Store et retourne ses variantes au format standard."""
        variants_list = []

        if card_el.get('data-producttype') != 'MTG Single':
            return []

        # Titre de la carte : supprimer le suffixe "(Showcase)", "(Phyrexian)", etc.
        title_el = card_el.select_one('.productCard__title')
        if not title_el:
            return []
        raw_title = title_el.get_text(strip=True)
        card_name = re.sub(r'\s*\(.*', '', raw_title).strip()

        link = card_el.select_one('a[href*="/products/"]')
        product_url = self.BASE_URL + link['href'] if link else self.BASE_URL

        # Set code depuis les tags produit
        tags_raw = card_el.get('data-producttags', '[]')
        try:
            tags = json.loads(tags_raw)
        except json.JSONDecodeError:
            tags = []

        set_code = self._set_code_from_tags(tags)

        # Variantes
        for variant_li in card_el.select('li[data-variantid]'):
            variant_title = variant_li.get('data-varianttitle', '')
            parsed = self.VARIANT_TITLE_MAP.get(variant_title)
            if parsed is None:
                print(f"  [SKIP] varianttitle inconnu: {variant_title!r}")
                continue
            condition, is_foil = parsed

            price_cents = variant_li.get('data-variantprice', '0')
            try:
                price = Decimal(price_cents) / 100
            except Exception:
                continue
            if price == 0:
                continue

            in_stock = variant_li.get('data-variantavailable', 'false').lower() == 'true'
            qty_raw = variant_li.get('data-variantqty', '')
            try:
                quantity = int(qty_raw) if qty_raw else None
            except ValueError:
                quantity = None

            variants_list.append({
                'name': card_name,
                'set_code': set_code,
                'collector_number': None,
                'price': price,
                'currency': 'CAD',
                'condition': condition,
                'foil': is_foil,
                'language': 'EN',
                'in_stock': in_stock,
                'stock_quantity': quantity,
                'url': product_url,
                'sku': variant_li.get('data-variantid', ''),
            })

        return variants_list

    def _set_code_from_tags(self, tags):
        """Trouve le set_code en essayant chaque tag candidat via la BD."""
        for tag in tags:
            if tag in self.NON_SET_TAGS:
                continue
            if tag not in self._set_code_cache:
                self._set_code_cache[tag] = self._resolve_set_code(tag)
            code = self._set_code_cache[tag]
            if code:
                return code
        return None

    def _resolve_set_code(self, set_name):
        """Trouve le set_code depuis le nom complet du set via la base de données."""
        if not set_name:
            return None
        try:
            from cards.models import Card
            card = Card.objects.filter(set_name__iexact=set_name).first()
            if card:
                return card.set_code
        except Exception:
            pass
        return None

    def save_prices(self, card, store):
        """
        Recherche par nom+set et sauvegarde sans filtrer par collector_number.

        The Mythic Store n'expose pas le numéro de collection.
        Tous les prix correspondant au nom + set de la carte sont sauvegardés.
        """
        from django.utils import timezone
        from cards.models import CardPrice

        products = self.search_card(card.name, card.set_code)
        if not products:
            return 0, 0

        products = [p for p in products if p['name'].lower() == card.name.lower()]

        created = 0
        updated = 0
        for product in products:
            _, was_created = CardPrice.objects.update_or_create(
                card=card,
                store=store,
                condition=product['condition'],
                foil=product['foil'],
                language=product['language'],
                defaults={
                    'price': product['price'],
                    'currency': product['currency'],
                    'in_stock': product['in_stock'],
                    'quantity': product['stock_quantity'],
                    'url': product['url'],
                    'scraped_at': timezone.now(),
                }
            )
            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated
