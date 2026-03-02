# backend/cards/management/commands/add_card_versions.py

from django.core.management.base import BaseCommand
from cards.models import Card
import requests
import time


class Command(BaseCommand):
    help = 'Ajoute toutes les versions d\'une carte depuis Scryfall'

    def add_arguments(self, parser):
        parser.add_argument(
            'card_name',
            type=str,
            help='Nom exact de la carte (ex: "Sheoldred, the Apocalypse")'
        )
        parser.add_argument(
            'set_code',
            type=str,
            help='Code du set (ex: DMU, SNC, NEO)'
        )
        parser.add_argument(
            '--track',
            action='store_true',
            help='Marquer les cartes comme trackées (is_tracked=True)'
        )

    def handle(self, *args, **options):
        card_name = options['card_name']
        set_code = options['set_code'].lower()
        track = options['track']
        
        self.stdout.write("\n" + "="*70)
        self.stdout.write(f"🔍 Recherche de toutes les versions de '{card_name}' dans {set_code.upper()}")
        self.stdout.write("="*70 + "\n")
        
        # Appel à l'API Scryfall
        url = "https://api.scryfall.com/cards/search"
        params = {
            'q': f'!"{card_name}" set:{set_code}',
            'unique': 'prints',
            'order': 'set'
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            if data.get('object') == 'error':
                self.stdout.write(self.style.ERROR(f"❌ Erreur Scryfall: {data.get('details')}"))
                return
            
            if data.get('object') != 'list':
                self.stdout.write(self.style.ERROR(f"❌ Réponse inattendue de Scryfall"))
                return
            
            cards_data = data.get('data', [])
            
            if not cards_data:
                self.stdout.write(self.style.WARNING(f"⚠️  Aucune carte trouvée pour '{card_name}' dans {set_code.upper()}"))
                return
            
            self.stdout.write(f"📦 {len(cards_data)} version(s) trouvée(s)\n")
            
            created_count = 0
            updated_count = 0
            skipped_count = 0
            
            for card_data in cards_data:
                # Extraire les informations
                scryfall_id = card_data['id']
                name = card_data['name']
                set_code_upper = card_data['set'].upper()
                set_name = card_data['set_name']
                collector_number = card_data['collector_number']
                rarity = card_data['rarity']
                
                # Image URL (priorité: normal > large > small)
                image_url = ''
                if 'image_uris' in card_data:
                    image_uris = card_data['image_uris']
                    image_url = image_uris.get('normal') or image_uris.get('large') or image_uris.get('small', '')
                elif 'card_faces' in card_data and card_data['card_faces']:
                    # Carte double-face
                    first_face = card_data['card_faces'][0]
                    if 'image_uris' in first_face:
                        image_url = first_face['image_uris'].get('normal', '')
                
                # Détecter le type de variante
                variant_info = self._get_variant_info(card_data)
                
                # Créer ou mettre à jour la carte
                card, created = Card.objects.update_or_create(
                    scryfall_id=scryfall_id,
                    defaults={
                        'name': name,
                        'set_code': set_code_upper,
                        'set_name': set_name,
                        'collector_number': collector_number,
                        'rarity': rarity,
                        'image_url': image_url,
                        'is_tracked': track
                    }
                )
                
                if created:
                    created_count += 1
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"✅ Créé: {name} #{collector_number} {variant_info}"
                        )
                    )
                else:
                    # Vérifier si on doit mettre à jour is_tracked
                    if track and not card.is_tracked:
                        card.is_tracked = True
                        card.save()
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f"🔄 Activé: {name} #{collector_number} {variant_info}"
                            )
                        )
                    else:
                        skipped_count += 1
                        self.stdout.write(
                            f"⚪ Existe: {name} #{collector_number} {variant_info}"
                        )
                
                # Respecter les limites de l'API Scryfall (100ms entre requêtes)
                time.sleep(0.1)
            
            # Statistiques finales
            self.stdout.write("\n" + "="*70)
            self.stdout.write("📊 RÉSUMÉ")
            self.stdout.write("="*70)
            self.stdout.write(f"Versions créées:      {created_count}")
            self.stdout.write(f"Versions activées:    {updated_count}")
            self.stdout.write(f"Versions existantes:  {skipped_count}")
            self.stdout.write("="*70 + "\n")
            
            if created_count > 0:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"✅ {created_count} nouvelle(s) version(s) ajoutée(s)!"
                    )
                )
            
            if track:
                self.stdout.write(
                    self.style.SUCCESS(
                        "\n💡 Ces cartes seront maintenant scrapées automatiquement."
                    )
                )
            else:
                self.stdout.write(
                    self.style.WARNING(
                        "\n💡 Utilisez --track pour activer le scraping automatique."
                    )
                )
            
            self.stdout.write("")
            
        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"❌ Erreur de connexion à Scryfall: {e}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Erreur inattendue: {e}"))

    def _get_variant_info(self, card_data):
        """Extrait les informations sur la variante de la carte"""
        frame_effects = card_data.get('frame_effects', [])
        promo_types = card_data.get('promo_types', [])
        border_color = card_data.get('border_color', 'black')
        finishes = card_data.get('finishes', [])
        
        info_parts = []
        
        # Frame effects (Showcase, Extended Art, etc.)
        if 'showcase' in frame_effects:
            info_parts.append('Showcase')
        if 'extendedart' in frame_effects:
            info_parts.append('Extended Art')
        if 'borderless' in frame_effects:
            info_parts.append('Borderless')
        
        # Promo types
        if 'prerelease' in promo_types:
            info_parts.append('Prerelease')
        if 'datestamped' in promo_types:
            info_parts.append('Datestamped')
        
        # Border
        if border_color == 'borderless':
            info_parts.append('Borderless')
        elif border_color == 'gold':
            info_parts.append('Gold Border')
        elif border_color == 'silver':
            info_parts.append('Silver Border')
        
        # Finishes
        if 'foil' in finishes and 'nonfoil' not in finishes:
            info_parts.append('Foil Only')
        elif 'etched' in finishes:
            info_parts.append('Etched Foil')
        
        if info_parts:
            return f"({', '.join(info_parts)})"
        return "(Normal)"