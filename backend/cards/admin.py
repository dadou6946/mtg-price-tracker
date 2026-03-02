# backend/apps/cards/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Card, Store, CardPrice


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ['name', 'location', 'is_active', 'created_at']
    list_filter = ['is_active', 'location']
    search_fields = ['name', 'url']
    readonly_fields = ['created_at']


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = [
        'name', 
        'set_code', 
        'collector_number',
        'rarity', 
        'is_tracked',
        'image_preview',
        'created_at'
    ]
    list_filter = ['set_code', 'rarity', 'is_tracked']
    search_fields = ['name', 'scryfall_id', 'set_name']
    readonly_fields = ['scryfall_id', 'created_at', 'updated_at', 'image_preview']
    
    fieldsets = (
        ('Informations principales', {
            'fields': ('name', 'scryfall_id')
        }),
        ('Extension', {
            'fields': ('set_code', 'set_name', 'collector_number')
        }),
        ('Métadonnées', {
            'fields': ('rarity', 'image_url', 'image_preview')
        }),
        ('Gestion', {
            'fields': ('is_tracked', 'created_at', 'updated_at')
        }),
    )
    
    def image_preview(self, obj):
        """Affiche un aperçu de l'image de la carte"""
        if obj.image_url:
            return format_html(
                '<img src="{}" style="max-width: 200px; max-height: 280px;" />',
                obj.image_url
            )
        return "Pas d'image"
    image_preview.short_description = "Aperçu"


@admin.register(CardPrice)
class CardPriceAdmin(admin.ModelAdmin):
    list_display = [
        'card',
        'store',
        'price',
        'currency',
        'condition',
        'foil_badge',
        'stock_badge',
        'scraped_at'
    ]
    list_filter = [
        'store',
        'condition',
        'foil',
        'in_stock',
        'language',
        'currency'
    ]
    search_fields = ['card__name', 'store__name']
    readonly_fields = ['scraped_at']
    date_hierarchy = 'scraped_at'
    
    fieldsets = (
        ('Produit', {
            'fields': ('card', 'store')
        }),
        ('Prix', {
            'fields': ('price', 'currency')
        }),
        ('Caractéristiques', {
            'fields': ('condition', 'language', 'foil')
        }),
        ('Stock', {
            'fields': ('in_stock', 'quantity')
        }),
        ('Métadonnées', {
            'fields': ('url', 'scraped_at')
        }),
    )
    
    def foil_badge(self, obj):
        """Badge visuel pour le foil"""
        if obj.foil:
            return format_html(
                '<span style="background-color: #ffd700; color: black; padding: 3px 8px; border-radius: 3px;">✨ Foil</span>'
            )
        return format_html(
            '<span style="background-color: #e0e0e0; color: black; padding: 3px 8px; border-radius: 3px;">Non-Foil</span>'
        )
    foil_badge.short_description = "Foil"
    
    def stock_badge(self, obj):
        """Badge visuel pour le stock"""
        if obj.in_stock:
            return format_html(
                '<span style="background-color: #4caf50; color: white; padding: 3px 8px; border-radius: 3px;">✓ En stock</span>'
            )
        return format_html(
            '<span style="background-color: #f44336; color: white; padding: 3px 8px; border-radius: 3px;">✗ Rupture</span>'
        )
    stock_badge.short_description = "Stock"