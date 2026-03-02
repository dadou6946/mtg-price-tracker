from rest_framework import serializers
from .models import Card, Store, CardPrice
from django.db.models import Min, Max
from django.utils import timezone
from datetime import timedelta

class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Store
        fields = ['id', 'name', 'url', 'location', 'is_active']

class CardPriceSerializer(serializers.ModelSerializer):
    store_name = serializers.CharField(source='store.name', read_only=True)
    card_name = serializers.CharField(source='card.name', read_only=True)
    
    class Meta:
        model = CardPrice
        fields = [
            'id', 'card', 'card_name', 'store', 'store_name',
            'price', 'currency', 'condition', 'language', 'foil',
            'in_stock', 'quantity', 'url', 'scraped_at'
        ]

class CardListSerializer(serializers.ModelSerializer):
    """Pour la liste des cartes (sans trop de détails)"""
    current_min_price = serializers.SerializerMethodField()
    current_max_price = serializers.SerializerMethodField()
    stores_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Card
        fields = [
            'id', 'scryfall_id', 'name', 'set_code', 'set_name',
            'collector_number', 'rarity', 'image_url', 'is_tracked',
            'current_min_price', 'current_max_price', 'stores_count'
        ]
    
    def get_current_min_price(self, obj):
        """Prix minimum actuel parmi tous les magasins"""
        latest_prices = self._get_latest_prices(obj)
        if latest_prices:
            return min(p.price for p in latest_prices)
        return None
    
    def get_current_max_price(self, obj):
        """Prix maximum actuel parmi tous les magasins"""
        latest_prices = self._get_latest_prices(obj)
        if latest_prices:
            return max(p.price for p in latest_prices)
        return None
    
    def get_stores_count(self, obj):
        """Nombre de magasins qui ont cette carte"""
        return CardPrice.objects.filter(card=obj, in_stock=True).values('store').distinct().count()
    
    def _get_latest_prices(self, obj):
        """Helper pour obtenir les derniers prix de chaque magasin"""
        # Récupère le dernier prix de chaque magasin
        from django.db.models import OuterRef, Subquery
        
        latest = CardPrice.objects.filter(
            card=obj,
            store=OuterRef('store'),
            in_stock=True
        ).order_by('-scraped_at')
        
        return CardPrice.objects.filter(
            card=obj,
            id__in=Subquery(latest.values('id')[:1])
        )

class CardDetailSerializer(serializers.ModelSerializer):
    """Pour les détails d'une carte (avec historique)"""
    current_prices = serializers.SerializerMethodField()
    price_history = serializers.SerializerMethodField()
    lowest_price = serializers.SerializerMethodField()
    
    class Meta:
        model = Card
        fields = [
            'id', 'scryfall_id', 'name', 'set_code', 'set_name',
            'collector_number', 'rarity', 'image_url', 'is_tracked',
            'created_at', 'current_prices', 'price_history', 'lowest_price'
        ]
    
    def get_current_prices(self, obj):
        """Dernier prix de chaque magasin"""
        from django.db.models import OuterRef, Subquery
        
        # Sous-requête pour obtenir l'ID du dernier prix par magasin
        latest_subquery = CardPrice.objects.filter(
            card=obj,
            store=OuterRef('store')
        ).order_by('-scraped_at').values('id')[:1]
        
        # Récupère les prix correspondants
        latest_prices = CardPrice.objects.filter(
            card=obj,
            id__in=Subquery(latest_subquery)
        ).select_related('store')
        
        return CardPriceSerializer(latest_prices, many=True).data
    
    def get_price_history(self, obj):
        """Historique des 30 derniers jours"""
        thirty_days_ago = timezone.now() - timedelta(days=30)
        history = CardPrice.objects.filter(
            card=obj,
            scraped_at__gte=thirty_days_ago
        ).select_related('store').order_by('scraped_at')
        
        return CardPriceSerializer(history, many=True).data
    
    def get_lowest_price(self, obj):
        """Prix le plus bas actuel"""
        latest_prices = CardPrice.objects.filter(
            card=obj,
            in_stock=True
        ).order_by('price').first()
        
        if latest_prices:
            return CardPriceSerializer(latest_prices).data
        return None