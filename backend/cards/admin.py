# backend/apps/cards/admin.py

from django.contrib import admin
from django.utils.html import format_html
from .models import Card, Store, CardPrice, StoreCircuitBreaker, TaskFailureLog


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


@admin.register(StoreCircuitBreaker)
class StoreCircuitBreakerAdmin(admin.ModelAdmin):
    list_display = [
        'store',
        'state_badge',
        'error_count',
        'error_threshold',
        'total_errors',
        'recovered_count',
        'opened_at',
    ]
    list_filter = ['state', 'store']
    readonly_fields = ['opened_at', 'closed_at']
    actions = ['reset_to_closed']

    def state_badge(self, obj):
        """Badge visuel pour l'état du circuit"""
        color_map = {
            'closed': '#4caf50',  # Green
            'open': '#f44336',    # Red
            'half_open': '#ff9800',  # Orange
        }
        color = color_map.get(obj.state, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.get_state_display(),
        )
    state_badge.short_description = "État"

    def reset_to_closed(self, request, queryset):
        """Action pour réinitialiser les circuit breakers en CLOSED"""
        updated = queryset.update(state='closed', error_count=0)
        self.message_user(request, f"{updated} circuit breaker(s) réinitialisé(s) en CLOSED")
    reset_to_closed.short_description = "Réinitialiser en CLOSED"


@admin.register(TaskFailureLog)
class TaskFailureLogAdmin(admin.ModelAdmin):
    list_display = [
        'task_name',
        'error_type_badge',
        'attempt_count',
        'is_resolved_badge',
        'failed_at',
    ]
    list_filter = ['error_type', 'is_resolved', 'is_retryable', 'failed_at']
    search_fields = ['task_name', 'task_id', 'error_message']
    readonly_fields = ['task_id', 'failed_at', 'resolved_at', 'traceback']
    date_hierarchy = 'failed_at'
    actions = ['mark_as_resolved', 'retry_tasks']

    fieldsets = (
        ('Tâche', {
            'fields': ('task_name', 'task_id', 'task_args', 'task_kwargs')
        }),
        ('Erreur', {
            'fields': ('error_type', 'error_message', 'traceback')
        }),
        ('Tentatives', {
            'fields': ('attempt_count', 'max_retries', 'is_retryable')
        }),
        ('Statut', {
            'fields': ('is_resolved', 'failed_at', 'resolved_at')
        }),
    )

    def error_type_badge(self, obj):
        """Badge visuel pour le type d'erreur"""
        color_map = {
            'RATE_LIMITED': '#ff9800',
            'SERVICE_UNAVAILABLE': '#f44336',
            'TIMEOUT': '#2196f3',
            'CONNECTION_ERROR': '#f44336',
            'SERVER_ERROR': '#f44336',
            'UNKNOWN': '#999',
        }
        color = color_map.get(obj.error_type, '#999')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 8px; border-radius: 3px;">{}</span>',
            color,
            obj.error_type,
        )
    error_type_badge.short_description = "Type d'erreur"

    def is_resolved_badge(self, obj):
        """Badge pour le statut"""
        if obj.is_resolved:
            return format_html(
                '<span style="background-color: #4caf50; color: white; padding: 3px 8px; border-radius: 3px;">✓ Résolu</span>'
            )
        return format_html(
            '<span style="background-color: #f44336; color: white; padding: 3px 8px; border-radius: 3px;">✗ Failé</span>'
        )
    is_resolved_badge.short_description = "Statut"

    def mark_as_resolved(self, request, queryset):
        """Action pour marquer comme résolu"""
        count = 0
        for log in queryset:
            log.mark_resolved()
            count += 1
        self.message_user(request, f"{count} tâche(s) marquée(s) comme résolue(s)")
    mark_as_resolved.short_description = "Marquer comme résolu"

    def retry_tasks(self, request, queryset):
        """Action pour retenter les tâches (à implémenter)"""
        count = 0
        for log in queryset.filter(is_retryable=True, is_resolved=False):
            # TODO: Implémenter la logique de retry
            count += 1
        self.message_user(request, f"{count} tâche(s) prête(s) pour retry")
    retry_tasks.short_description = "Retenter les tâches"