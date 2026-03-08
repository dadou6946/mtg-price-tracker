# backend/apps/cards/models.py

import logging
from django.db import models
from django.utils import timezone

logger = logging.getLogger('cards.models')


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


class StoreCircuitBreaker(models.Model):
    """
    Circuit Breaker pattern pour les magasins.

    Évite de marteler un magasin qui crashe ou rate-limite.
    États:
    - CLOSED: Normal, les requêtes passent
    - OPEN: Trop d'erreurs, on skipe ce magasin
    - HALF_OPEN: Test pour voir si le magasin est revenu
    """
    CLOSED = 'closed'      # Normal
    OPEN = 'open'          # Magasin down/rate-limit
    HALF_OPEN = 'half_open'  # Test en cours

    STATE_CHOICES = [
        (CLOSED, 'Closed (Actif)'),
        (OPEN, 'Open (Paused)'),
        (HALF_OPEN, 'Half-Open (Testing)'),
    ]

    store = models.OneToOneField(Store, on_delete=models.CASCADE, related_name='circuit_breaker')

    # État du circuit
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=CLOSED)

    # Compteur d'erreurs
    error_count = models.IntegerField(default=0, help_text="Nombre d'erreurs consécutives")
    error_threshold = models.IntegerField(default=5, help_text="Seuil avant OPEN")

    # Timeout avant tentative de récupération
    last_error_at = models.DateTimeField(null=True, blank=True)
    timeout_seconds = models.IntegerField(default=300, help_text="Secondes avant HALF_OPEN (5 min par défaut)")

    # Statistiques
    total_errors = models.IntegerField(default=0, help_text="Total d'erreurs historiques")
    recovered_count = models.IntegerField(default=0, help_text="Nombre de fois récupéré")

    # Timestamps
    opened_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.store.name} - {self.state}"

    class Meta:
        verbose_name = "Circuit Breaker"
        verbose_name_plural = "Circuit Breakers"

    def is_available(self):
        """Retourne True si on peut scraper ce magasin."""
        from datetime import timedelta
        from django.utils import timezone

        if self.state == self.CLOSED:
            return True

        if self.state == self.OPEN:
            # Check si timeout écoulé pour passer en HALF_OPEN
            if self.last_error_at:
                elapsed = timezone.now() - self.last_error_at
                if elapsed.total_seconds() > self.timeout_seconds:
                    # Permet un test en transitant par HALF_OPEN
                    self.state = self.HALF_OPEN
                    self.save(update_fields=['state'])
                    return True
            return False

        # HALF_OPEN: permet les requêtes (test)
        return True

    def record_success(self):
        """Enregistre un succès (réinitialise les erreurs)."""
        if self.state == self.HALF_OPEN:
            # Récupération après OPEN
            logger.info(f"Circuit breaker {self.store.name}: HALF_OPEN -> CLOSED (recovered)")
            self.state = self.CLOSED
            self.recovered_count += 1
            self.closed_at = timezone.now()
        else:
            logger.debug(f"Circuit breaker {self.store.name}: success, error_count reset")

        self.error_count = 0
        self.save(update_fields=['state', 'error_count', 'recovered_count', 'closed_at'])

    def record_error(self):
        """Enregistre une erreur, passe potentiellement en OPEN."""
        from django.utils import timezone

        # Si erreur en HALF_OPEN, repasser immédiatement en OPEN (test échoué)
        if self.state == self.HALF_OPEN:
            logger.warning(f"Circuit breaker {self.store.name}: HALF_OPEN -> OPEN (recovery failed)")
            self.state = self.OPEN
            self.error_count = 1
            self.total_errors += 1
            self.last_error_at = timezone.now()
            self.opened_at = timezone.now()
            self.save(update_fields=['state', 'error_count', 'total_errors', 'last_error_at', 'opened_at'])
            return

        # Mode CLOSED: compter les erreurs
        self.error_count += 1
        self.total_errors += 1
        self.last_error_at = timezone.now()

        if self.error_count >= self.error_threshold:
            # Passage en OPEN
            logger.warning(f"Circuit breaker {self.store.name}: CLOSED -> OPEN (threshold reached: {self.error_count}/{self.error_threshold})")
            self.state = self.OPEN
            self.opened_at = timezone.now()
        else:
            logger.debug(f"Circuit breaker {self.store.name}: error #{self.error_count}/{self.error_threshold}")

        self.save(update_fields=['state', 'error_count', 'total_errors', 'last_error_at', 'opened_at'])


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


class PriceHistory(models.Model):
    """
    Historique agrégé des prix pour une carte

    Snapshot quotidien des prix min/max/moyen pour tracker l'évolution.
    Utilisé pour les graphiques et analyses de tendances.
    """
    # Relations
    card = models.ForeignKey(
        Card,
        on_delete=models.CASCADE,
        related_name='price_history'
    )

    # Prix agrégés (condition NM non-foil par défaut)
    price_min = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Prix minimum trouvé"
    )
    price_max = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Prix maximum trouvé"
    )
    price_avg = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        help_text="Prix moyen"
    )

    # Métadonnées
    stores_count = models.IntegerField(
        default=0,
        help_text="Nombre de magasins avec ce prix"
    )
    in_stock_count = models.IntegerField(
        default=0,
        help_text="Nombre de magasins en stock"
    )

    # Timestamp
    scraped_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Date du scraping"
    )

    class Meta:
        indexes = [
            models.Index(fields=['card', '-scraped_at']),
            models.Index(fields=['-scraped_at']),
        ]
        ordering = ['-scraped_at']
        verbose_name = "Historique Prix"
        verbose_name_plural = "Historiques Prix"
        # Éviter les doublons : 1 entry par jour par carte max
        unique_together = [['card', 'scraped_at']]

    def __str__(self):
        return f"{self.card.name} - {self.scraped_at.date()}: ${self.price_avg}"

    @property
    def price_range(self):
        """Range de prix (max - min)"""
        return self.price_max - self.price_min