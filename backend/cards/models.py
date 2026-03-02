# backend/apps/cards/models.py

from django.db import models
from django.utils import timezone


class Store(models.Model):
    """Magasins de cartes Magic à Montréal"""
    name = models.CharField(max_length=100)
    url = models.URLField()
    location = models.CharField(max_length=100, default="Montréal")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name
    
    class Meta:
        verbose_name = "Magasin"
        verbose_name_plural = "Magasins"


class Card(models.Model):
    """
    Carte Magic: The Gathering
    
    Chaque version d'une carte (normale, showcase, extended art, etc.) 
    est une entrée séparée identifiée par son collector_number unique.
    """
    # Identifiants
    scryfall_id = models.CharField(
        max_length=36, 
        unique=True,
        help_text="ID unique Scryfall (UUID)"
    )
    
    # Informations de base
    name = models.CharField(max_length=200)
    set_code = models.CharField(
        max_length=10,
        help_text="Code de l'extension (ex: SNC, DMU, NEO)"
    )
    set_name = models.CharField(
        max_length=100,
        help_text="Nom complet de l'extension"
    )
    collector_number = models.CharField(
        max_length=10,
        help_text="Numéro de collectionneur (identifie la version spécifique)"
    )
    
    # Métadonnées
    rarity = models.CharField(
        max_length=20,
        choices=[
            ('common', 'Commune'),
            ('uncommon', 'Peu commune'),
            ('rare', 'Rare'),
            ('mythic', 'Mythique rare'),
            ('special', 'Spéciale')
        ]
    )
    image_url = models.URLField(blank=True, help_text="URL de l'image de la carte")
    
    # Gestion
    is_tracked = models.BooleanField(
        default=True,
        help_text="Si True, cette carte sera scrapée automatiquement"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        # Combinaison unique : même nom peut avoir plusieurs versions
        unique_together = [['name', 'set_code', 'collector_number']]
        indexes = [
            models.Index(fields=['name', 'set_code']),
            models.Index(fields=['is_tracked']),
            models.Index(fields=['scryfall_id']),
        ]
        ordering = ['name', 'set_code', 'collector_number']
        verbose_name = "Carte"
        verbose_name_plural = "Cartes"
    
    def __str__(self):
        return f"{self.name} ({self.set_code}) #{self.collector_number}"
    
    @property
    def display_name(self):
        """Nom d'affichage avec la version"""
        return f"{self.name} #{self.collector_number}"


class CardPrice(models.Model):
    """
    Prix d'une carte dans un magasin spécifique
    
    Historise tous les prix pour permettre le suivi dans le temps.
    """
    # Relations
    card = models.ForeignKey(
        Card, 
        on_delete=models.CASCADE,
        related_name='prices'
    )
    store = models.ForeignKey(
        Store, 
        on_delete=models.CASCADE,
        related_name='prices'
    )
    
    # Prix
    price = models.DecimalField(
        max_digits=10, 
        decimal_places=2,
        help_text="Prix en devise locale"
    )
    currency = models.CharField(
        max_length=3, 
        default="CAD",
        choices=[
            ('CAD', 'Dollar canadien'),
            ('USD', 'Dollar américain'),
            ('EUR', 'Euro')
        ]
    )
    
    # Caractéristiques du produit
    condition = models.CharField(
        max_length=20,
        default="NM",
        choices=[
            ('NM', 'Near Mint'),
            ('LP', 'Lightly Played'),
            ('MP', 'Moderately Played'),
            ('HP', 'Heavily Played'),
            ('DMG', 'Damaged')
        ],
        help_text="État de la carte"
    )
    language = models.CharField(
        max_length=10,
        default="EN",
        choices=[
            ('EN', 'Anglais'),
            ('FR', 'Français'),
            ('PHY', 'Phyrexian'),
            ('JP', 'Japonais'),
            ('DE', 'Allemand'),
            ('ES', 'Espagnol'),
            ('IT', 'Italien'),
            ('PT', 'Portugais'),
            ('RU', 'Russe'),
            ('KO', 'Coréen'),
            ('ZHS', 'Chinois simplifié'),
            ('ZHT', 'Chinois traditionnel')
        ]
    )
    foil = models.BooleanField(
        default=False,
        help_text="True si la carte est foil"
    )
    
    # Stock
    in_stock = models.BooleanField(default=True)
    quantity = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Quantité disponible (si connue)"
    )
    
    # Métadonnées
    url = models.URLField(help_text="URL du produit sur le site du magasin")
    scraped_at = models.DateTimeField(
        default=timezone.now,
        help_text="Date et heure du scraping"
    )
    
    class Meta:
        indexes = [
            models.Index(fields=['card', 'store', '-scraped_at']),
            models.Index(fields=['card', 'condition', 'foil']),
            models.Index(fields=['in_stock']),
            models.Index(fields=['-scraped_at']),
        ]
        ordering = ['-scraped_at']
        verbose_name = "Prix"
        verbose_name_plural = "Prix"
    
    def __str__(self):
        foil_text = " (Foil)" if self.foil else ""
        return f"{self.card.name} - {self.store.name}: {self.price} {self.currency} ({self.condition}){foil_text}"
    
    @property
    def is_recent(self):
        """True si le prix a été scrapé dans les dernières 24h"""
        from django.utils import timezone
        from datetime import timedelta
        return self.scraped_at > timezone.now() - timedelta(days=1)