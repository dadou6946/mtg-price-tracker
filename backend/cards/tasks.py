import time
import requests
from celery import shared_task, group, chord
from concurrent.futures import ThreadPoolExecutor, as_completed


def _extract_image_url(card_data):
    if 'image_uris' in card_data:
        return card_data['image_uris'].get('normal', '')
    if 'card_faces' in card_data and card_data['card_faces']:
        return card_data['card_faces'][0].get('image_uris', {}).get('normal', '')
    return ''


@shared_task(bind=True)
def import_card_task(self, name, set_code=None, track=False):
    """Importe une carte depuis Scryfall et la sauvegarde en BD."""
    from cards.models import Card

    if set_code:
        url = f"https://api.scryfall.com/cards/named?exact={requests.utils.quote(name)}&set={set_code}"
    else:
        url = f"https://api.scryfall.com/cards/named?fuzzy={requests.utils.quote(name)}"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return {'status': 'error', 'message': f"Carte '{name}' introuvable sur Scryfall"}
        return {'status': 'error', 'message': f"Erreur Scryfall HTTP {e.response.status_code}"}
    except requests.RequestException as e:
        return {'status': 'error', 'message': str(e)}

    existing = Card.objects.filter(scryfall_id=data['id']).first()
    if existing:
        return {
            'status': 'skipped',
            'message': 'Carte deja en BD',
            'card': {
                'id': existing.id,
                'name': existing.name,
                'set_code': existing.set_code,
                'collector_number': existing.collector_number,
            },
        }

    card = Card.objects.create(
        scryfall_id=data['id'],
        name=data['name'],
        set_code=data['set'].upper(),
        set_name=data['set_name'],
        collector_number=data['collector_number'],
        rarity=data['rarity'],
        image_url=_extract_image_url(data),
        is_tracked=track,
    )

    return {
        'status': 'created',
        'card': {
            'id': card.id,
            'name': card.name,
            'set_code': card.set_code,
            'collector_number': card.collector_number,
            'rarity': card.rarity,
        },
    }


@shared_task(bind=True)
def import_set_task(self, set_code, rarities=None, track=False):
    """Importe toutes les cartes d'un set depuis Scryfall selon les raretés choisies."""
    from cards.models import Card

    if rarities is None:
        rarities = ['rare', 'mythic']

    set_code = set_code.upper()

    if len(rarities) == 1:
        rarity_filter = f"rarity:{rarities[0]}"
    else:
        rarity_filter = "(" + " or ".join(f"rarity:{r}" for r in rarities) + ")"

    all_cards = []
    url = "https://api.scryfall.com/cards/search"
    params = {'q': f"set:{set_code.lower()} {rarity_filter} -is:arena", 'unique': 'prints', 'order': 'set'}
    page = 1

    while url:
        try:
            response = requests.get(url, params=params if page == 1 else None, timeout=10)
            response.raise_for_status()
        except requests.HTTPError as e:
            if e.response.status_code == 404:
                return {'status': 'error', 'message': f"Set '{set_code}' introuvable sur Scryfall"}
            return {'status': 'error', 'message': f"Erreur Scryfall HTTP {e.response.status_code}"}
        except requests.RequestException as e:
            return {'status': 'error', 'message': str(e)}

        data = response.json()
        if data.get('object') == 'error':
            return {'status': 'error', 'message': data.get('details')}

        batch = data.get('data', [])
        all_cards.extend(batch)

        # Progression
        self.update_state(
            state='PROGRESS',
            meta={'fetched': len(all_cards), 'page': page},
        )

        if data.get('has_more') and data.get('next_page'):
            url = data['next_page']
            page += 1
            time.sleep(0.1)
        else:
            break

    created = updated = skipped = 0

    for card_data in all_cards:
        card, was_created = Card.objects.update_or_create(
            scryfall_id=card_data['id'],
            defaults={
                'name': card_data['name'],
                'set_code': card_data['set'].upper(),
                'set_name': card_data['set_name'],
                'collector_number': card_data['collector_number'],
                'rarity': card_data['rarity'],
                'image_url': _extract_image_url(card_data),
                'is_tracked': track,
            },
        )

        if was_created:
            created += 1
        elif track and not card.is_tracked:
            card.is_tracked = True
            card.save(update_fields=['is_tracked'])
            updated += 1
        else:
            skipped += 1

    return {
        'status': 'done',
        'set_code': set_code,
        'total': len(all_cards),
        'created': created,
        'updated': updated,
        'skipped': skipped,
    }


def _scrape_store(scraper_class, card, store, max_retries=3):
    """Scrape une carte sur un seul store (pour parallélisation) avec retries sur database locked et rate-limiting."""
    import time

    for attempt in range(max_retries):
        try:
            scraper = scraper_class()
            created, updated = scraper.save_prices(card, store)
            return store.name, {'created': created, 'updated': updated}
        except Exception as e:
            error_msg = str(e).lower()
            is_db_locked = 'database is locked' in error_msg or 'locked' in error_msg
            is_rate_limited = '429' in error_msg or 'too many requests' in error_msg
            is_service_unavailable = '503' in error_msg or 'service unavailable' in error_msg

            should_retry = (is_db_locked or is_rate_limited or is_service_unavailable) and attempt < max_retries - 1

            if should_retry:
                # Retry avec backoff exponentiel: 1s, 2s, 4s...
                wait_time = 1 * (2 ** attempt)
                time.sleep(wait_time)
                continue

            # Dernier essai ou erreur non-retry → retourner l'erreur
            return store.name, {'error': str(e)}


@shared_task(bind=True)
def scrape_card_task(self, card_id):
    """Scrape les prix d'une carte sur tous les stores actifs (en parallèle)."""
    import random
    from cards.models import Card, Store, CardPrice, PriceHistory
    from scrapers import SCRAPER_REGISTRY
    from django.utils import timezone
    from datetime import datetime

    # Petit delay aléatoire pour étaler les requêtes entre workers
    delay = random.uniform(0, 1.5)
    time.sleep(delay)

    card = Card.objects.get(id=card_id)
    stores = list(Store.objects.filter(is_active=True))
    results = {}

    # Paralléliser le scraping des stores avec ThreadPoolExecutor (max 3 threads pour respecter les stores)
    with ThreadPoolExecutor(max_workers=min(len(stores), 3)) as executor:
        futures = {}

        for i, store in enumerate(stores):
            scraper_class = SCRAPER_REGISTRY.get(store.name)
            if not scraper_class:
                results[store.name] = {'skipped': True}
                continue

            future = executor.submit(_scrape_store, scraper_class, card, store)
            futures[future] = (store.name, i + 1)

        # Traiter les résultats au fur et à mesure qu'ils se complètent
        completed = 0
        for future in as_completed(futures):
            store_name, idx = futures[future]
            try:
                name, result = future.result()
                results[name] = result
            except Exception as e:
                results[store_name] = {'error': str(e)}

            completed += 1
            self.update_state(
                state='PROGRESS',
                meta={'completed': completed, 'total': len(futures), 'store': store_name},
            )

    # Sauvegarder un snapshot dans PriceHistory (NM non-foil)
    try:
        prices_nm = CardPrice.objects.filter(
            card=card,
            condition='NM',
            foil=False
        )

        if prices_nm.exists():
            prices_list = [float(p.price) for p in prices_nm if p.price]
            if prices_list:
                PriceHistory.objects.create(
                    card=card,
                    price_min=min(prices_list),
                    price_max=max(prices_list),
                    price_avg=sum(prices_list) / len(prices_list),
                    stores_count=prices_nm.count(),
                    in_stock_count=prices_nm.filter(in_stock=True).count(),
                )
    except Exception as e:
        # Pas critique si ça échoue, juste log
        pass

    return {
        'status': 'done',
        'card': {'id': card.id, 'name': card.name, 'set_code': card.set_code},
        'stores': results,
        'total_created': sum(r.get('created', 0) for r in results.values()),
        'total_updated': sum(r.get('updated', 0) for r in results.values()),
    }


def _aggregate_scrape_results(results):
    """Agrège les résultats des sous-tâches scrape_card_task."""
    total_created = total_updated = errors = 0

    for result in results:
        if result and isinstance(result, dict):
            total_created += result.get('total_created', 0)
            total_updated += result.get('total_updated', 0)

    return {
        'status': 'done',
        'total_cards': len(results),
        'total_created': total_created,
        'total_updated': total_updated,
        'errors': errors,
    }


@shared_task
def aggregate_scrape_results(results):
    """Callback : agrège les résultats après que toutes les sous-tâches complètent."""
    return _aggregate_scrape_results(results)


@shared_task(bind=True)
def scrape_all_task(self):
    """Scrape toutes les cartes trackées sur tous les stores actifs (distribuées aux 7 workers en parallèle)."""
    from cards.models import Card

    cards = list(Card.objects.filter(is_tracked=True))
    total = len(cards)

    if total == 0:
        return {'status': 'done', 'message': 'Aucune carte trackee', 'total_cards': 0}

    # Utiliser chord() : exécute toutes les sous-tâches, puis agrège les résultats
    # chord(header)(callback) : lance header en parallèle, puis exécute callback avec les résultats
    job = chord(scrape_card_task.s(card.id) for card in cards)(aggregate_scrape_results.s())

    # Retourner le statut immédiatement (la tâche tourner en background)
    return {
        'status': 'processing',
        'total_cards': total,
        'message': f'{total} cartes en cours de scraping en parallèle...',
        'chord_id': job.id,  # ID de la tâche callback qui aura les résultats finaux
    }
