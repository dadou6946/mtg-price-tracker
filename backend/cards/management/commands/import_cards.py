from django.core.management.base import BaseCommand
from cards.models import Card
import requests
import time

class Command(BaseCommand):
    help = 'Importe des cartes depuis Scryfall API'

    def add_arguments(self, parser):
        parser.add_argument(
            'card_names',
            nargs='+',
            type=str,
            help='Noms des cartes à importer'
        )
        parser.add_argument(
            '--set',
            type=str,
            help='Code de l\'édition (ex: SNC, MH3)',
            default=None
        )
        parser.add_argument(
            '--no-track',
            action='store_true',
            help='Ne pas suivre automatiquement les cartes importées'
        )

    def handle(self, *args, **options):
        card_names = options['card_names']
        set_code = options.get('set')
        track = not options.get('no_track', False)
        
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(f"📥 Import de {len(card_names)} carte(s) depuis Scryfall")
        self.stdout.write(f"{'='*60}\n")
        
        imported = 0
        skipped = 0
        errors = 0
        
        for card_name in card_names:
            result = self.import_card(card_name, set_code, track)
            if result == 'imported':
                imported += 1
            elif result == 'skipped':
                skipped += 1
            else:
                errors += 1
            
            # Rate limiting Scryfall (max 10 requêtes/seconde)
            time.sleep(0.15)
        
        # Résumé
        self.stdout.write(f"\n{'='*60}")
        self.stdout.write(self.style.SUCCESS(f"✅ {imported} carte(s) importée(s)"))
        if skipped > 0:
            self.stdout.write(self.style.WARNING(f"⏭️  {skipped} carte(s) déjà existante(s)"))
        if errors > 0:
            self.stdout.write(self.style.ERROR(f"❌ {errors} erreur(s)"))
        self.stdout.write(f"{'='*60}\n")

    def import_card(self, card_name, set_code=None, track=True):
        """
        Importe une carte depuis Scryfall
        
        Args:
            card_name (str): Nom de la carte
            set_code (str, optional): Code de l'édition
            track (bool): Marquer la carte comme suivie
        
        Returns:
            str: 'imported', 'skipped', ou 'error'
        """
        # Construction de l'URL Scryfall
        if set_code:
            # Recherche exacte par nom + set
            url = f"https://api.scryfall.com/cards/named?exact={card_name}&set={set_code}"
        else:
            # Recherche fuzzy (tolérante aux fautes)
            url = f"https://api.scryfall.com/cards/named?fuzzy={card_name}"
        
        try:
            self.stdout.write(f"🔍 Recherche: {card_name}" + (f" ({set_code})" if set_code else ""))
            
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Vérifie si la carte existe déjà
            existing = Card.objects.filter(scryfall_id=data['id']).first()
            
            if existing:
                self.stdout.write(
                    self.style.WARNING(f"   ⏭️  Déjà existante: {existing.name} ({existing.set_code})")
                )
                return 'skipped'
            
            # Gère les cartes double-face
            image_url = ''
            if 'image_uris' in data:
                image_url = data['image_uris'].get('normal', '')
            elif 'card_faces' in data and data['card_faces']:
                # Prend l'image de la première face
                image_url = data['card_faces'][0].get('image_uris', {}).get('normal', '')
            
            # Crée la carte
            card = Card.objects.create(
                scryfall_id=data['id'],
                name=data['name'],
                set_code=data['set'].upper(),
                set_name=data['set_name'],
                collector_number=data['collector_number'],
                rarity=data['rarity'],
                image_url=image_url,
                is_tracked=track,
            )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f"   ✅ Importée: {card.name} ({card.set_code}) - {card.rarity}"
                )
            )
            
            return 'imported'
        
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Carte non trouvée: {card_name}")
                )
            else:
                self.stdout.write(
                    self.style.ERROR(f"   ❌ Erreur HTTP {e.response.status_code}: {card_name}")
                )
            return 'error'
        
        except requests.RequestException as e:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Erreur réseau pour {card_name}: {e}")
            )
            return 'error'
        
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f"   ❌ Erreur inattendue pour {card_name}: {e}")
            )
            return 'error'