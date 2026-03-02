from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CardViewSet, StoreViewSet, CardPriceViewSet

router = DefaultRouter()
router.register(r'cards', CardViewSet, basename='card')
router.register(r'stores', StoreViewSet, basename='store')
router.register(r'prices', CardPriceViewSet, basename='price')

urlpatterns = [
    path('', include(router.urls)),
]