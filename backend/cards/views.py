import logging
from celery.result import AsyncResult
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django_filters.rest_framework import DjangoFilterBackend

from .models import Card, Store, CardPrice
from .serializers import (
    CardListSerializer, CardDetailSerializer,
    StoreSerializer, CardPriceSerializer,
)
from .tasks import import_card_task, import_set_task, scrape_card_task, scrape_all_task
from .throttling import ScrapeThrottle, ImportThrottle

logger = logging.getLogger('cards.views')


class StoreViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Store.objects.filter(is_active=True)
    serializer_class = StoreSerializer


class CardViewSet(viewsets.ModelViewSet):
    """
    GET  /api/cards/               - Liste (filtres: set_code, rarity, is_tracked, search)
    GET  /api/cards/{id}/          - Détail + prix + historique
    POST /api/cards/import/        - Importer une carte depuis Scryfall (async)
    POST /api/cards/import_set/    - Importer un set complet depuis Scryfall (async)
    POST /api/cards/{id}/scrape/   - Scraper les prix de cette carte (async)
    POST /api/cards/{id}/toggle_tracking/ - Activer/désactiver le suivi
    GET  /api/cards/tracked/       - Cartes suivies uniquement
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
        tracked_cards = self.get_queryset().filter(is_tracked=True)
        page = self.paginate_queryset(tracked_cards)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(tracked_cards, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def toggle_tracking(self, request, pk=None):
        card = self.get_object()
        card.is_tracked = not card.is_tracked
        card.save()
        serializer = self.get_serializer(card)
        return Response({
            'message': f"Suivi {'active' if card.is_tracked else 'desactive'}",
            'card': serializer.data,
        })

    @action(detail=False, methods=['post'], url_path='import', throttle_classes=[ImportThrottle])
    def import_card(self, request):
        """
        Importe une carte depuis Scryfall.

        Body: { "name": "Goldspan Dragon", "set_code": "KHM", "track": false }
        Retourne: { "task_id": "...", "status": "queued" }
        """
        name = request.data.get('name', '').strip()
        if not name:
            logger.warning("Import card requested without name")
            return Response({'error': 'Le champ "name" est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        set_code = request.data.get('set_code', '').strip().upper() or None
        track = bool(request.data.get('track', False))

        logger.info(f"Queuing import_card_task: {name} (set={set_code}, track={track})")
        task = import_card_task.delay(name, set_code, track)
        return Response({'task_id': task.id, 'status': 'queued'}, status=status.HTTP_202_ACCEPTED)

    @action(detail=False, methods=['post'], url_path='import_set', throttle_classes=[ImportThrottle])
    def import_set(self, request):
        """
        Importe toutes les cartes d'un set depuis Scryfall.

        Body: { "set_code": "KHM", "rarities": ["rare", "mythic"], "track": false }
        Retourne: { "task_id": "...", "status": "queued" }
        """
        set_code = request.data.get('set_code', '').strip().upper()
        if not set_code:
            return Response({'error': 'Le champ "set_code" est requis.'}, status=status.HTTP_400_BAD_REQUEST)

        rarities = request.data.get('rarities', ['rare', 'mythic'])
        valid = {'common', 'uncommon', 'rare', 'mythic'}
        invalid = [r for r in rarities if r not in valid]
        if invalid:
            return Response(
                {'error': f'Raretés invalides : {invalid}. Valeurs acceptées : {sorted(valid)}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        track = bool(request.data.get('track', False))

        task = import_set_task.delay(set_code, rarities, track)
        return Response({'task_id': task.id, 'status': 'queued'}, status=status.HTTP_202_ACCEPTED)

    @action(detail=True, methods=['post'], throttle_classes=[ScrapeThrottle])
    def scrape(self, request, pk=None):
        """
        Scrape les prix de cette carte sur tous les stores actifs.

        Retourne: { "task_id": "...", "status": "queued" }
        """
        card = self.get_object()
        task = scrape_card_task.delay(card.id)
        return Response({'task_id': task.id, 'status': 'queued'}, status=status.HTTP_202_ACCEPTED)


class ScrapeAllView(APIView):
    """
    POST /api/scrape/
    Lance un scrape complet de toutes les cartes trackées.
    Retourne: { "task_id": "...", "status": "queued" }
    """
    throttle_classes = [ScrapeThrottle]

    def post(self, request):
        task = scrape_all_task.delay()
        return Response({'task_id': task.id, 'status': 'queued'}, status=status.HTTP_202_ACCEPTED)


class TaskStatusView(APIView):
    """
    GET /api/tasks/{task_id}/
    Retourne le statut et le résultat d'une tâche Celery.

    Statuts possibles :
      PENDING   - en attente (ou task_id inconnu)
      STARTED   - démarrée
      PROGRESS  - en cours (meta: données de progression)
      SUCCESS   - terminée avec succès (result: données)
      FAILURE   - erreur (error: message)
    """
    def get(self, request, task_id):
        result = AsyncResult(task_id)

        response = {'task_id': task_id, 'status': result.state}

        if result.state == 'PROGRESS':
            response['progress'] = result.info
        elif result.state == 'SUCCESS':
            response['result'] = result.result
        elif result.state == 'FAILURE':
            response['error'] = str(result.result)

        return Response(response)


class CardPriceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CardPrice.objects.all().select_related('card', 'store')
    serializer_class = CardPriceSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['card', 'store', 'foil', 'in_stock', 'condition']
    ordering_fields = ['price', 'scraped_at']
    ordering = ['-scraped_at']
