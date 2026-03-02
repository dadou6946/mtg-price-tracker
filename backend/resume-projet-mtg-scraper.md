# Résumé du Projet - Veille Tarifaire Magic: The Gathering

## 🎯 OBJECTIF DU PROJET

Développer une application web de **suivi de prix pour cartes Magic: The Gathering** qui scrape automatiquement les boutiques de Montréal (Face to Face Games principalement) pour suivre l'évolution des prix et disponibilités.

### Enjeux Business
- **Veille concurrentielle** : Suivre les fluctuations de prix sur le marché secondaire MTG
- **Opportunités d'achat** : Identifier les meilleurs moments pour acheter/vendre des cartes
- **Analyse de marché** : Comprendre les tendances de prix par édition, rareté, format compétitif
- **Gestion de collection** : Optimiser la valeur de sa collection personnelle

### Enjeux Techniques
- **Scraping dynamique** : Face to Face charge les prix via JavaScript (besoin de Selenium)
- **Données complexes** : Multiples conditions (NM, PL, MP, HP) avec stocks différents par condition
- **Multi-versions** : Une même carte peut avoir plusieurs versions (standard, foil, extended art, etc.)
- **Volume** : Des milliers de cartes à tracker régulièrement

---

## 🏗️ ARCHITECTURE TECHNIQUE

### Stack
- **Backend** : Django (Python)
- **Frontend** : Vue.js
- **Scraping** : Selenium + BeautifulSoup
- **Base de données** : PostgreSQL/SQLite (Django ORM)

### Modèles Django Principaux

```python
# models.py
class Card(models.Model):
    name = models.CharField(max_length=255)
    set_name = models.CharField(max_length=255)
    collector_number = models.CharField(max_length=50)  # Clé importante!
    variant = models.CharField(max_length=255)  # "Non-Foil", "Foil Extended Art", etc.
    # ... autres champs

class Price(models.Model):
    card = models.ForeignKey(Card)
    store = models.CharField(max_length=255)  # "Face to Face Games"
    price_cad = models.DecimalField()
    condition = models.CharField(max_length=10)  # "NM", "PL", "MP", "HP"
    in_stock = models.BooleanField()
    stock_quantity = models.IntegerField()
    scrape_date = models.DateTimeField(auto_now_add=True)
```

### API de Recherche
- **Endpoint** : `/api/search/`
- **Scraper actuel** : `scrapers/face_to_face_v2.py`
- **Fonctionnalité** : Recherche une carte sur Face to Face et retourne les prix en temps réel

---

## 🐛 PROBLÈME ACTUEL

### Symptômes
1. **Condition manquante** : Certains prix affichent `condition = "-"` au lieu de `"PL"`
2. **Stock incorrect** : Tous les prix marqués "Rupture de stock" alors que certains sont disponibles
3. **Données incomplètes** : Pour une carte donnée, seul le prix NM est capturé, le prix PL est ignoré

### Exemple Concret (Fable of the Mirror-Breaker #465)
Face to Face affiche **2 lignes de prix** :
```
NM (5)    16.99$  ← 5 exemplaires en stock
PL (0)    13.59$  ← 0 exemplaire en stock
```

Mais la base de données ne contient qu'**1 prix** :
```
Condition: "-"
Stock: Rupture
Prix: 16.99$
```

### Cause Racine Identifiée

**Le scraper actuel (`face_to_face_v2.py`) utilise 2 méthodes complémentaires :**

1. **Parsing JavaScript** (`var meta = {...}`)
   - ✅ Contient les SKUs et données de base
   - ❌ Ne contient qu'**un seul variant par SKU**
   - ❌ Les différentes conditions (NM/PL/MP/HP) ne sont pas distinguées dans ce JSON

2. **Parsing HTML** (via BeautifulSoup)
   - ✅ Contient les URLs des produits
   - ❌ Ne parse **pas les lignes de prix individuelles**

**Résultat** : Le scraper manque les informations de condition et de stock qui sont **uniquement dans le HTML**, dans des lignes séparées pour chaque condition.

---

## 💡 SOLUTION DÉVELOPPÉE

### Approche : Parser HTML Directement

Au lieu de se fier au JavaScript `var meta`, créer un parser qui lit **directement le HTML de la page de recherche** pour extraire :
- Toutes les conditions disponibles (NM, PL, MP, HP)
- Le stock pour chaque condition
- Le prix pour chaque condition

### Fichier Créé : `face_to_face_html_parser.py`

**Logique du parser :**

```python
# Regex pour extraire condition + quantité + prix
# Exemple: "NM (5) 16.99$"
pattern = r'(NM|PL|MP|HP)\s*\((\d+)\)\s*([\d,]+\.?\d*)\$'

# Pour chaque produit dans le HTML :
for product in soup.find_all('div', class_='product-card'):
    # Extraire nom, collector_number, variant
    name = product.find('h3').text
    collector = extract_collector_number(product)
    variant = product.find('div', class_='variant').text
    
    # Extraire TOUTES les lignes de prix
    for price_row in product.find_all('div', class_='price-row'):
        match = re.search(pattern, price_row.text)
        if match:
            condition = match.group(1)  # "NM" ou "PL"
            quantity = int(match.group(2))  # 5 ou 0
            price = float(match.group(3))  # 16.99
            in_stock = quantity > 0
            
            # Créer un objet Price pour CHAQUE condition
            create_price(card, condition, price, quantity, in_stock)
```

**Avantages :**
- ✅ Capture toutes les conditions (NM, PL, MP, HP)
- ✅ Stock réel pour chaque condition
- ✅ Plusieurs prix par carte (une ligne par condition disponible)

---

## 📋 STATUT ACTUEL DU DÉVELOPPEMENT

### ✅ Réalisé
1. ✅ Modèle Django avec `collector_number` (permet de distinguer les versions)
2. ✅ API de recherche fonctionnelle (`face_to_face_v2.py`)
3. ✅ Panneau d'administration Django qui affiche le `collector_number`
4. ✅ Fix du bug "multi-versions" : les prix sont maintenant correctement associés au bon collector_number
5. ✅ Création du parser HTML (`face_to_face_html_parser.py`) avec logique regex
6. ✅ Réception du **fichier HTML source** de Face to Face (2.2MB)

### 🔄 En Cours / Bloqué
1. 🔄 **Finalisation du parser HTML** : Besoin d'analyser le HTML réel pour :
   - Identifier les **vrais noms de classes CSS** (ex: `product-card`, `price-row`)
   - Trouver la **structure exacte** des éléments (divs, spans, etc.)
   - Ajuster les **sélecteurs CSS** pour qu'ils correspondent au HTML réel

2. 🔄 **Intégration** : Remplacer `face_to_face_v2.py` par le nouveau parser HTML

3. ⏳ **Tests** : Vérifier avec les 3 versions de Fable (#141, #357, #465) que :
   - Chaque version a 2 prix (NM + PL)
   - Les stocks sont corrects
   - Les conditions sont bien identifiées

### 📁 Fichiers Clés

```
mtg_pricer/
├── scrapers/
│   ├── face_to_face_v2.py          # Scraper actuel (JavaScript meta)
│   └── face_to_face_html_parser.py # Nouveau parser HTML (EN COURS)
├── management/commands/
│   └── scrape_face_to_face.py      # Management command Django
├── models.py                        # Card, Price models
└── admin.py                         # Admin panel config
```

**Fichier HTML source uploadé :**
- `/mnt/user-data/uploads/view-source_https___facetofacegames.com_fr_search_q=fable-of-the-mirror-breaker.html`
- Taille : 2.2MB
- Contenu : HTML complet de la page de recherche Face to Face

---

## 🎯 PROCHAINES ÉTAPES POUR CLAUDE CODE

### Étape 1 : Analyser le HTML Source
1. Ouvrir le fichier HTML uploadé
2. Identifier la structure réelle :
   - Comment les produits sont organisés ? (class, id, structure)
   - Où se trouvent les lignes de prix ?
   - Comment les conditions (NM/PL) sont-elles affichées ?
   - Où se trouve le collector_number ?

### Étape 2 : Finaliser `face_to_face_html_parser.py`
1. Remplacer les sélecteurs CSS génériques par les vrais
2. Adapter les regex si nécessaire
3. Tester le parsing sur le HTML réel

### Étape 3 : Intégration
1. Modifier le management command pour utiliser le nouveau parser
2. Tester avec plusieurs cartes
3. Vérifier en base de données

### Étape 4 : Tests de Validation
**Test avec "Fable of the Mirror-Breaker"** :
- Rechercher "fable-of-the-mirror-breaker"
- Vérifier qu'on obtient **3 cartes** (versions #141, #357, #465)
- Chaque carte doit avoir **2 prix minimum** (NM + PL si disponible)
- Les stocks doivent être corrects
- Les conditions doivent être "NM", "PL", etc. (pas "-")

---

## 🔑 POINTS D'ATTENTION

### Données Critiques à Capturer
1. **collector_number** : Absolument essentiel pour distinguer les versions
2. **condition** : NM, PL, MP, HP (pas de "-" ou None)
3. **stock_quantity** : Nombre réel d'exemplaires disponibles
4. **in_stock** : Boolean dérivé de stock_quantity > 0

### Cas Particuliers
- Certaines cartes n'ont qu'une seule condition disponible (ex: seulement NM)
- Certaines cartes sont en rupture totale (toutes conditions à 0)
- Les prix peuvent être identiques entre conditions (rare mais possible)

### Performance
- Face to Face utilise du JavaScript dynamique → **Selenium obligatoire**
- Prévoir des délais entre requêtes pour éviter d'être bloqué
- Cacher les résultats quand possible

---

## 💬 CONTEXTE UTILISATEUR

L'utilisateur (David) :
- 🎮 Joueur compétitif de Magic à Montréal
- 🏪 Client régulier de Face to Face Games
- 💻 Développeur (Django + Vue.js)
- 🇫🇷 Francophone
- 🎯 Objectif : Optimiser ses achats de cartes en suivant les prix

---

## 🚀 OBJECTIF FINAL

**Application de veille tarifaire complète qui permet de :**
1. Rechercher n'importe quelle carte MTG
2. Voir les prix en temps réel de toutes les boutiques de Montréal
3. Comparer les conditions et stocks disponibles
4. Suivre l'historique des prix dans le temps
5. Recevoir des alertes quand un prix baisse

**Étape actuelle** : Finaliser le scraping Face to Face avec conditions et stocks corrects.
