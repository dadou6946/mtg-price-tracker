from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CardViewSet, StoreViewSet, CardPriceViewSet, ScrapeAllView, TaskStatusView

router = DefaultRouter()
router.register(r'cards', CardViewSet, basename='card')
router.register(r'stores', StoreViewSet, basename='store')
router.register(r'prices', CardPriceViewSet, basename='price')

urlpatterns = [
    path('', include(router.urls)),
    path('scrape/', ScrapeAllView.as_view(), name='scrape-all'),
    path('tasks/<str:task_id>/', TaskStatusView.as_view(), name='task-status'),
]
