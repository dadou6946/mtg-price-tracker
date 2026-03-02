# Documentation — Système de scraping MTG Price Tracker

## Table des matières

1. [Vue d'ensemble](#vue-densemble)
2. [Architecture](#architecture)
3. [Format standardisé](#format-standardisé)
4. [Technologies de scraping](#technologies-de-scraping)
5. [Tableau des stores](#tableau-des-stores)
6. [Commande scrape](#commande-scrape)
7. [Limitations connues](#limitations-connues)
8. [Ajouter un nouveau store](#ajouter-un-nouveau-store)

---

## Vue d'ensemble

Le système scrape les prix de cartes MTG depuis 12 boutiques canadiennes.
Pour chaque carte suivie, il récupère toutes ses variantes (condition, foil, langue)
et les sauvegarde dans la table `CardPrice`.

**Pipeline général :**

```
scrape --store "X" --card-name "Y"
        │
        ▼
scraper.search_card(name, set_code)
        │
        ├─ GET /search?q=name&page=1..N
        ├─ Extraire les produits (var meta ou HTML)
        ├─ Parser chaque variante → format standard
        └─ Filtrer par set_code
        │
        ▼
_scrape_by_name() ou save_prices()
        │
        ├─ Matcher avec Card en BD (par collector_number ou nom)
        └─ CardPrice.update_or_create(card, store, condition, foil, langue)
```

---

## Architecture

```
scrapers/
├── base.py              # BaseScraper (ABC) — interface + save_prices()
├── __init__.py          # SCRAPER_REGISTRY {store_name: ScraperClass}
├── crystal_commerce.py  # BaseCrystalCommerceScraper — base partagée CC
│
├── face_to_face.py      # Shopify var meta — SKU propre à FtF
├── le_coin_du_jeu.py    # Shopify var meta
├── goblin_argent.py     # Shopify var meta
├── remi_card_trader.py  # Shopify var meta
├── multizone.py         # Shopify var meta
├── altf4.py             # Shopify var meta — pagination intensive
├── three_dragons.py     # Shopify var meta
│
├── le_valet_de_coeur.py      # Crystal Commerce
├── secret_des_korrigans.py   # Crystal Commerce
├── expedition.py             # Crystal Commerce
├── topdeck_hero.py           # Crystal Commerce — SSL_VERIFY=False
│
└── mythic_store.py      # Shopify thème custom — BeautifulSoup
```

### BaseScraper (`base.py`)

Classe abstraite dont héritent tous les scrapers.

- **`search_card(name, set_code)`** — à implémenter, retourne une liste de variantes
- **`save_prices(card, store)`** — scrape + sauvegarde en BD, retourne `(créés, mis à jour)`
  - Filtre par `collector_number` si la carte en a un
  - Surcharge possible (CC, Mythic Store) quand pas de collector_number

### SCRAPER_REGISTRY (`__init__.py`)

Dictionnaire `{store_name: ScraperClass}`. La clé doit correspondre exactement
au champ `Store.name` en base de données. Le registre est utilisé par la commande
`scrape` pour instancier les scrapers.

---

## Format standardisé

Chaque variante retournée par `search_card()` est un dictionnaire :

| Champ             | Type         | Description                          |
|-------------------|--------------|--------------------------------------|
| `name`            | `str`        | Nom de la carte (nettoyé)            |
| `set_code`        | `str`        | Code du set (`DMU`, `NEO`…)          |
| `collector_number`| `str\|None`  | Numéro de collection (`107`, `290`…) |
| `price`           | `Decimal`    | Prix en CAD                          |
| `currency`        | `str`        | `'CAD'` (toujours)                   |
| `condition`       | `str`        | `NM`, `LP`, `MP`, `HP`, `DMG`        |
| `foil`            | `bool`       | `True` si foil                       |
| `language`        | `str`        | `EN`, `FR`, `JP`, `PHY`…             |
| `in_stock`        | `bool`       | Disponibilité                        |
| `stock_quantity`  | `int\|None`  | Quantité en stock si disponible      |
| `url`             | `str`        | URL de la page produit               |
| `sku`             | `str`        | Identifiant interne du store         |

**Conditions normalisées :**

| Valeur | Signification      |
|--------|--------------------|
| `NM`   | Near Mint          |
| `LP`   | Lightly Played     |
| `MP`   | Moderately Played  |
| `HP`   | Heavily Played     |
| `DMG`  | Damaged            |

**Codes langue :** `EN`, `FR`, `JP`, `DE`, `ES`, `IT`, `KO`, `RU`, `PT`, `ZHS`, `ZHT`, `PHY`

---

## Technologies de scraping

### 1. Shopify `var meta`

Utilisé par : FtF, LCdJ, Goblin, Rémi, Multizone, Alt F4, 3 Dragons

Shopify injecte dans chaque page HTML un bloc JavaScript :
```js
var meta = {
  "products": [
    {
      "id": 12345,
      "handle": "sheoldred-the-apocalypse-dominaria-united",
      "variants": [
        { "sku": "DMU-107-EN-NF-1", "public_title": "Near Mint", "price": 14999 }
      ]
    }
  ]
};
```

**Extraction :**
```python
match = re.search(r'var meta\s*=\s*(\{.*?\});', html, re.DOTALL)
meta = json.loads(match.group(1))
products = meta.get('products', [])
```

**Informations clés :**
- `price` est en **centimes** → diviser par 100
- `available` est systématiquement `None` → on pose `in_stock=True` par défaut
- `public_title` contient la condition + foil sous forme lisible
- Le **SKU** contient set_code, collector_number, langue, foil, condition

**Pagination :** quand la page N dépasse les résultats, Shopify renvoie les mêmes
produits que la page 1 → déduplication par `product_id` (`seen_ids`).

**Formats de SKU par store :**

| Store | Format | Exemple |
|-------|--------|---------|
| Face to Face | `TYPE-GAME-SET-COL-LANG-COND[-FOIL]` | `MTG-SINGLE-DMU-107-ENG-NM-F` |
| LCdJ / Goblin / Rémi / Multizone | `SET-COL-[EXTRA-]LANG-FOIL-COND` | `DMU-107-EN-NF-1` |
| 3 Dragons | `SET-COL-COND-FOIL` | `DMU-107-NM-N` |
| Alt F4 | numérique inutile | `12345` |

Pour les SKU à longueur variable (Rémi, Multizone), extraction robuste :
```python
parts = sku.split('-')
set_code        = parts[0]
collector_number = parts[1]
language        = next(p for p in reversed(parts[2:-2]) if p in LANGUAGE_CODES)
# parts[-2] = foil (NF/FO), parts[-1] = numéro condition
```

**Cas particulier Alt F4 :** le SKU est inutile. Le set_code et le collector_number
sont extraits du champ `name` via regex : `[SET - COLLECTOR]`.

---

### 2. Crystal Commerce

Utilisé par : Le Valet de Coeur, Le Secret des Korrigans, L'Expédition, Topdeck Hero

Plateforme e-commerce distincte de Shopify. Les données sont dans le HTML
(pas de JSON embarqué) :

```html
<li class="product">
  <div class="variant-row in-stock">
    <span class="variant-short-info variant-qty">3 En stock</span>
    <form class="add-to-cart-form"
          data-vid="abc123"
          data-name="Sheoldred, the Apocalypse - Foil"
          data-variant="NM-Mint, English"
          data-price="CAD$ 14.99"
          data-category="Dominaria United">
  </div>
</li>
```

**Extraction :** BeautifulSoup — `li.product` → `form.add-to-cart-form`

**Informations clés :**
- Les formulaires sont répétés 3× (vue grille / liste / détail) → dédup par `data-vid`
- `data-variant` : `"NM-Mint, English"` → condition + langue
- `data-category` : nom complet du set → résolu en `set_code` via la BD
- `data-name` : nom de la carte + suffixes variant (Foil, Showcase…)
- Stock : classe CSS `in-stock` sur le `div.variant-row` parent
- **Pas de `collector_number`** (limitation de la plateforme)

**Résolution du set_code :**
```python
def _resolve_set_code(self, set_name):
    card = Card.objects.filter(set_name__iexact=set_name).first()
    return card.set_code if card else None
```

**Particularités par store :**

| Store | Différence |
|-------|-----------|
| Le Valet | Paramètre `c=1` (filtre MTG) |
| L'Expédition | Paramètre `c=1`, 3e champ variant = succursale (ignoré) |
| Topdeck Hero | `SSL_VERIFY=False` (certificat non reconnu sur Windows) ; conditions typo (`Moderatly Played`, `Brand New`) ; collector number dans le nom |
| Korrigans | Aucune particularité |

---

### 3. Shopify thème personnalisé

Utilisé par : The Mythic Store

Shopify sans le `var meta` standard. Les données sont dans des attributs HTML
sur des éléments personnalisés :

```html
<div class="productCard__card"
     data-productid="7511078371488"
     data-producttype="MTG Single"
     data-producttags='["Black","Dominaria United","Mythic","Normal"]'>

  <h3 class="productCard__title">Sheoldred, the Apocalypse</h3>
  <a href="/products/sheoldred-the-apocalypse-dominaria-united">

  <ul>
    <li data-variantid="123"
        data-varianttitle="Near Mint Foil"
        data-variantprice="15699"
        data-variantavailable="true"
        data-variantqty="2">
  </ul>
</div>
```

**Extraction :** BeautifulSoup — `div.productCard__card` → `li[data-variantid]`

**Informations clés :**
- `data-variantprice` en centimes → diviser par 100
- `data-varianttitle` contient condition + foil (`"Near Mint Foil"`)
- `data-producttags` : tableau JSON contenant le nom du set
- URL de recherche non standard : `/a/search?q=...`
- **Pas de `collector_number`**

**Résolution du set_code depuis les tags :**
```python
NON_SET_TAGS = {'Black', 'Mythic', 'Standard', 'Foil', 'Normal', ...}

def _set_code_from_tags(self, tags):
    for tag in tags:
        if tag in self.NON_SET_TAGS:
            continue
        if tag not in self._set_code_cache:
            self._set_code_cache[tag] = self._resolve_set_code(tag)
        if self._set_code_cache[tag]:
            return self._set_code_cache[tag]
    return None
```

---

## Tableau des stores

| Store | Techno | collector_number | URL recherche | Notes |
|-------|--------|:-:|---|---|
| Face to Face Games | Shopify var meta | ✅ | `/fr/search?q=` | SKU format propre FtF |
| Le Coin du Jeu | Shopify var meta | ✅ | `/search?q=` | |
| Le Goblin d'Argent | Shopify var meta | ✅ | `/fr/search?q=` | Préfixe `MTG-` possible |
| Rémi Card Trader | Shopify var meta | ✅ | `/search?q=` | SKU 5-7 parts, subdomain `singles.` |
| Multizone | Shopify var meta | ✅ | `/search?q=*nom*` | Wildcards dans la query |
| Alt F4 | Shopify var meta | ✅ | `/search?q=` | Moteur de recherche peu fiable, MAX_PAGES=15 |
| 3 Dragons | Shopify var meta | ✅ | `/fr/search?q=` | SKU 4 parts, handle=UUID, URL `/fr/products/` |
| Le Valet de Coeur | Crystal Commerce | ❌ | `/products/search?c=1` | |
| Le Secret des Korrigans | Crystal Commerce | ❌ | `/products/search` | |
| L'Expédition | Crystal Commerce | ❌ | `/products/search?c=1` | 3e champ = succursale |
| Topdeck Hero | Crystal Commerce | ❌ | `/products/search` | SSL_VERIFY=False |
| The Mythic Store | Shopify custom | ❌ | `/a/search?q=` | BeautifulSoup, tags JSON |

**Stores actifs en BD :** Face to Face, Le Coin du Jeu, Le Valet de Coeur,
Le Goblin d'Argent, Le Secret des Korrigans, L'Expédition, Topdeck Hero,
The Mythic Store, Multizone

---

## Commande scrape

```bash
# Tous les stores, toutes les cartes suivies
python manage.py scrape

# Un store spécifique
python manage.py scrape --store "Face to Face Games"

# Recherche par nom (sans sauvegarder, affiche les résultats)
python manage.py scrape --store "Multizone" --card-name "Sheoldred, the Apocalypse"

# Recherche + filtre set + toutes les versions
python manage.py scrape --store "Multizone" \
  --card-name "Sheoldred, the Apocalypse" --set DMU --all-versions
```

**Mode `--card-name` :**
1. Appelle `search_card(name, set_code)`
2. Groupe les résultats par `(set_code, collector_number)` — ou `(set, nom)` si pas de numéro
3. Pour chaque version, cherche la `Card` correspondante en BD
4. Sauvegarde les prix (`CardPrice.update_or_create`)
5. Sans `--all-versions` : s'arrête après la première version trouvée

**Mode sans `--card-name` (scrape toutes les cartes suivies) :**
1. Récupère toutes les `Card` avec `is_tracked=True`
2. Pour chaque carte, appelle `scraper.save_prices(card, store)`
3. Délai de 1.5s entre chaque carte (politesse serveur)

**Lancer sous Windows (encodage) :**
```bash
set PYTHONIOENCODING=utf-8 && venv/Scripts/python manage.py scrape ...
```

---

## Limitations connues

### Stores sans `collector_number` (CC + Mythic Store)

Crystal Commerce et The Mythic Store n'exposent pas le numéro de collection.
Le matching se fait par `nom + set_code` uniquement. Si un set contient plusieurs
cartes homonymes avec des collector numbers différents (ex: versions showcase,
borderless…), elles reçoivent toutes les mêmes prix. `save_prices()` est surchargée
dans ces scrapers pour filtrer par nom exact plutôt que par collector_number.

### Alt F4 — moteur de recherche peu fiable

La recherche Shopify de altf4online.com ignore parfois les filtres ou retourne
les résultats pertinents en fin de pagination. `MAX_PAGES=15` pour compenser.
Les cartes en rupture de stock n'apparaissent pas du tout dans les résultats.

### Topdeck Hero — certificat SSL

Le certificat SSL de topdeckhero.com n'est pas reconnu par Python sur Windows.
`SSL_VERIFY = False` est défini sur ce scraper, ce qui génère des avertissements
`urllib3.InsecureRequestWarning` (ignorables dans ce contexte).

### Stock toujours `True` sur Shopify var meta

Le champ `available` dans `var meta` est systématiquement `None` sur la plupart
des stores Shopify (FtF, LCdJ, Rémi, Multizone, Alt F4, 3 Dragons).
`in_stock=True` est posé par défaut. Seul Crystal Commerce expose le stock réel
(classe CSS `in-stock` + quantité dans le HTML).

---

## Ajouter un nouveau store

### Checklist

1. **Analyser la page de recherche HTML** — identifier la techno (Shopify var meta ?
   Crystal Commerce ? autre ?) et le format des données (SKU, conditions, langue…)

2. **Créer `scrapers/nom_store.py`** en héritant de la bonne base :
   - Shopify var meta → hériter de `BaseScraper`, copier le pattern Rémi/Multizone
   - Crystal Commerce → hériter de `BaseCrystalCommerceScraper`, implémenter `_search_params()`
   - Thème custom → hériter de `BaseScraper`, parser avec BeautifulSoup

3. **Définir les constantes :**
   - `STORE_NAME` — doit correspondre exactement au `Store.name` en BD
   - `BASE_URL` / `SEARCH_URL`
   - `CONDITION_MAP` ou `PUBLIC_TITLE_MAP` — selon le format du store
   - `MAX_PAGES` — 5 par défaut, 15 si moteur de recherche peu fiable

4. **Enregistrer dans `scrapers/__init__.py`** :
   ```python
   from scrapers.nom_store import NomStoreScraper
   SCRAPER_REGISTRY["Nom du Store"] = NomStoreScraper
   ```

5. **Créer le store en BD** — ajouter dans `init_stores.py` puis :
   ```bash
   python manage.py init_stores
   ```

6. **Tester :**
   ```bash
   set PYTHONIOENCODING=utf-8 && venv/Scripts/python manage.py scrape \
     --store "Nom du Store" --card-name "Sheoldred, the Apocalypse" --set DMU --all-versions
   ```

### Template minimal (Shopify var meta)

```python
"""
Scraper pour NomStore (url.ca)
Shopify — var meta. SKU : SET-COL-LANG-FOIL-COND
"""
import re, json, time, requests
from decimal import Decimal
from scrapers.base import BaseScraper

class NomStoreScraper(BaseScraper):
    STORE_NAME = "Nom du Store"
    BASE_URL   = "https://url.ca"
    SEARCH_URL = f"{BASE_URL}/search"
    MAX_PAGES  = 5

    PUBLIC_TITLE_MAP = {
        'Near Mint': ('NM', False), 'Near Mint Foil': ('NM', True),
        'Lightly Played': ('LP', False), 'Lightly Played Foil': ('LP', True),
        'Moderately Played': ('MP', False), 'Moderately Played Foil': ('MP', True),
        'Heavily Played': ('HP', False), 'Heavily Played Foil': ('HP', True),
        'Damaged': ('DMG', False), 'Damaged Foil': ('DMG', True),
    }
    LANGUAGE_CODES = {'EN','FR','JP','DE','ES','IT','KO','PHY','RU','PT','ZHS','ZHT'}

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 ...'})

    def search_card(self, card_name, set_code=None):
        all_variants, seen_ids, page = [], set(), 1
        while page <= self.MAX_PAGES:
            r = self.session.get(self.SEARCH_URL, params={'q': card_name, 'page': page}, timeout=15)
            products = self._extract_meta_products(r.text)
            if not products: break
            new = [p for p in products if p.get('id') not in seen_ids]
            if not new: break
            for p in new:
                seen_ids.add(p['id'])
                all_variants.extend(self._parse_product(p))
            page += 1
            if page <= self.MAX_PAGES: time.sleep(1)
        if set_code:
            all_variants = [v for v in all_variants if v.get('set_code') == set_code]
        return all_variants

    def _extract_meta_products(self, html):
        m = re.search(r'var meta\s*=\s*(\{.*?\});', html, re.DOTALL)
        if not m: return []
        try: return json.loads(m.group(1)).get('products', [])
        except json.JSONDecodeError: return []

    def _parse_product(self, product):
        handle = product.get('handle', '')
        url = f"{self.BASE_URL}/products/{handle}"
        results = []
        for v in product.get('variants', []):
            sku = v.get('sku', '')
            parsed = self.PUBLIC_TITLE_MAP.get(v.get('public_title', ''))
            if not parsed: continue
            condition, is_foil = parsed
            parts = sku.split('-')
            if len(parts) < 5: continue
            set_code = parts[0]
            collector_number = parts[1]
            language = next((p for p in reversed(parts[2:-2]) if p in self.LANGUAGE_CODES), 'EN')
            results.append({
                'name': re.sub(r'\s*[\[(].*', '', v.get('name', '')).strip(),
                'set_code': set_code, 'collector_number': collector_number,
                'price': Decimal(v.get('price', 0)) / 100, 'currency': 'CAD',
                'condition': condition, 'foil': is_foil, 'language': language,
                'in_stock': True, 'stock_quantity': None, 'url': url, 'sku': sku,
            })
        return results
```
