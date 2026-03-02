from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from .models import Card, Store, CardPrice
from .serializers import (
    CardListSerializer, CardDetailSerializer, 
    StoreSerializer, CardPriceSerializer
)

class StoreViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API pour les magasins
    
    GET /api/stores/        - Liste tous les magasins actifs
    GET /api/stores/{id}/   - Détails d'un magasin
    """
    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer

class CardViewSet(viewsets.ModelViewSet):
    """
    API pour les cartes
    
    GET  /api/cards/          - Liste toutes les cartes
    POST /api/cards/          - Ajouter une carte
    GET  /api/cards/{id}/     - Détails d'une carte (avec historique)
    PUT  /api/cards/{id}/     - Modifier une carte
    DELETE /api/cards/{id}/   - Supprimer une carte
    
    Filtres disponibles:
    - ?set_code=MH3           - Par extension
    - ?rarity=mythic          - Par rareté
    - ?is_tracked=true        - Cartes suivies
    - ?search=lightning       - Recherche par nom
    """
    queryset = Card.objects.all()
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['set_code', 'rarity', 'is_tracked']
    search_fields = ['name', 'set_name']
    ordering_fields = ['name', 'set_code', 'created_at']
    ordering = ['-created_at']
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return CardDetailSerializer
        return CardListSerializer
    
    @action(detail=False, methods=['get'])
    def tracked(self, request):
        """
        Endpoint custom pour obtenir uniquement les cartes suivies
        GET /api/cards/tracked/
        """
        tracked_cards = self.get_queryset().filter(is_tracked=True)
        page = self.paginate_queryset(tracked_cards)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(tracked_cards, many=True)
        return Response(serializer.data)
    
    @action(detail=True, methods=['post'])
    def toggle_tracking(self, request, pk=None):
        """
        Active/désactive le suivi d'une carte
        POST /api/cards/{id}/toggle_tracking/
        """
        card = self.get_object()
        card.is_tracked = not card.is_tracked
        card.save()
        
        serializer = self.get_serializer(card)
        return Response({
            'message': f"Suivi {'activé' if card.is_tracked else 'désactivé'}",
            'card': serializer.data
        })

class CardPriceViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API pour les prix
    
    GET /api/prices/                    - Liste tous les prix
    GET /api/prices/{id}/               - Détails d'un prix
    GET /api/prices/?card=1             - Prix d'une carte spécifique
    GET /api/prices/?store=1            - Prix d'un magasin spécifique
    GET /api/prices/?in_stock=true      - Seulement les cartes en stock
    """
    queryset = CardPrice.objects.all().select_related('card', 'store')
    serializer_class = CardPriceSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['card', 'store', 'foil', 'in_stock', 'condition']
    ordering_fields = ['price', 'scraped_at']
    ordering = ['-scraped_at']