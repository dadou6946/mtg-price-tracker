"""
Importe toutes les cartes d'un set depuis Scryfall, filtrées par rareté.

Usage :
  python manage.py import_set DMU
  python manage.py import_set DMU --rarity rare mythic
  python manage.py import_set DMU --rarity rare --track
  python manage.py import_set DMU --no-track

Par défaut : rare + mythic, non suivies.

API Scryfall utilisée :
  GET /cards/search?q=set:DMU (rarity:rare or rarity:mythic)&unique=prints&order=set
  unique=prints  → retourne toutes les versions (showcase, borderless, prerelease...)
  Pagination via champ "next_page" dans la réponse.
"""
import time
import requests
from django.core.management.base import BaseCommand
from cards.models import Card


RARITY_CHOICES = ['common', 'uncommon', 'rare', 'mythic']

SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"


class Command(BaseCommand):
    help = "Importe toutes les cartes d'un set depuis Scryfall, filtrées par rareté"

    def add_arguments(self, parser):
        parser.add_argument(
            'set_code',
            type=str,
            help='Code du set (ex: DMU, MH3, DSK)',
        )
        parser.add_argument(
            '--rarity',
            nargs='+',
            choices=RARITY_CHOICES,
            default=['rare', 'mythic'],
            metavar='RARITY',
            help='Raretés à importer (défaut: rare mythic). Choix: common uncommon rare mythic',
        )
        parser.add_argument(
            '--track',
            action='store_true',
            default=False,
            help='Marquer les cartes comme suivies (is_tracked=True)',
        )
        parser.add_argument(
            '--no-track',
            action='store_true',
            default=False,
            help='Ne pas suivre les cartes (défaut)',
        )

    def handle(self, *args, **options):
        set_code = options['set_code'].upper()
        rarities = options['rarity']
        track = options['track'] and not options['no_track']

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"Import set : {set_code}")
        self.stdout.write(f"Raretés   : {', '.join(rarities)}")
        self.stdout.write(f"Tracking  : {'oui' if track else 'non'}")
        self.stdout.write(f"{'='*60}\n")

        cards_data = self._fetch_all_cards(set_code, rarities)
        if not cards_data:
            return

        self.stdout.write(f"\n{len(cards_data)} version(s) a importer...\n")
        self._import_cards(cards_data, track)

    # ------------------------------------------------------------------

    def _fetch_all_cards(self, set_code, rarities):
        """Récupère toutes les cartes via l'API Scryfall (pagination incluse)."""
        # Construction de la query Scryfall
        if len(rarities) == 1:
            rarity_filter = f"rarity:{rarities[0]}"
        else:
            rarity_filter = "(" + " or ".join(f"rarity:{r}" for r in rarities) + ")"

        query = f"set:{set_code.lower()} {rarity_filter}"

        params = {
            'q': query,
            'unique': 'prints',
            'order': 'set',
        }

        all_cards = []
        url = SCRYFALL_SEARCH_URL
        page = 1

        while url:
            self.stdout.write(f"  Scryfall page {page}...")
            try:
                response = requests.get(url, params=params if page == 1 else None, timeout=10)
                response.raise_for_status()
            except requests.HTTPError as e:
                if e.response.status_code == 404:
                    self.stdout.write(self.style.ERROR(
                        f"Set '{set_code}' introuvable sur Scryfall (ou aucune carte pour ces raretés)."
                    ))
                else:
                    self.stdout.write(self.style.ERROR(f"Erreur HTTP {e.response.status_code}"))
                return []
            except requests.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Erreur réseau : {e}"))
                return []

            data = response.json()

            if data.get('object') == 'error':
                self.stdout.write(self.style.ERROR(f"Scryfall : {data.get('details')}"))
                return []

            batch = data.get('data', [])
            all_cards.extend(batch)
            self.stdout.write(f"    {len(batch)} carte(s) recues (total: {len(all_cards)})")

            if data.get('has_more') and data.get('next_page'):
                url = data['next_page']
                page += 1
                time.sleep(0.1)  # Politesse Scryfall (max 10 req/s)
            else:
                break

        return all_cards

    def _import_cards(self, cards_data, track):
        """Crée ou met à jour les cartes en BD."""
        created = 0
        updated = 0
        skipped = 0

        for card_data in cards_data:
            scryfall_id  = card_data['id']
            name         = card_data['name']
            set_code     = card_data['set'].upper()
            set_name     = card_data['set_name']
            collector_number = card_data['collector_number']
            rarity       = card_data['rarity']
            image_url    = self._extract_image_url(card_data)

            card, was_created = Card.objects.update_or_create(
                scryfall_id=scryfall_id,
                defaults={
                    'name': name,
                    'set_code': set_code,
                    'set_name': set_name,
                    'collector_number': collector_number,
                    'rarity': rarity,
                    'image_url': image_url,
                    'is_tracked': track,
                }
            )

            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [NEW] {name} #{collector_number} ({rarity})"
                ))
            elif track and not card.is_tracked:
                # La carte existait mais n'était pas suivie → on l'active
                card.is_tracked = True
                card.save(update_fields=['is_tracked'])
                updated += 1
                self.stdout.write(self.style.SUCCESS(
                    f"  [ACT] {name} #{collector_number} (tracking active)"
                ))
            else:
                skipped += 1
                self.stdout.write(
                    f"  [--]  {name} #{collector_number} (deja en BD)"
                )

            time.sleep(0.05)  # Petit délai pour ne pas saturer la BD

        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"Crees   : {created}"))
        if updated:
            self.stdout.write(self.style.SUCCESS(f"Actives : {updated}"))
        self.stdout.write(f"Ignores : {skipped}")
        self.stdout.write(f"{'='*60}")

        if not track:
            self.stdout.write(self.style.WARNING(
                "\nAjoutez --track pour marquer ces cartes comme suivies."
            ))

    def _extract_image_url(self, card_data):
        """Extrait l'URL d'image (gère les cartes double-face)."""
        if 'image_uris' in card_data:
            uris = card_data['image_uris']
            return uris.get('normal') or uris.get('large') or uris.get('small', '')
        if 'card_faces' in card_data and card_data['card_faces']:
            face_uris = card_data['card_faces'][0].get('image_uris', {})
            return face_uris.get('normal', '')
        return ''
