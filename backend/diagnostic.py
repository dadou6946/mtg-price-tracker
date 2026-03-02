"""
Script de diagnostic pour Face to Face
Sauvegarde le HTML et affiche les sélecteurs trouvés
"""
import requests
from bs4 import BeautifulSoup
import re

BASE_URL = "https://www.facetofacegames.com"
SEARCH_URL = f"{BASE_URL}/fr/search"

# Recherche Fable
params = {'q': 'fable-of-the-mirror-breaker'}

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept-Language': 'fr-FR,fr;q=0.9,en;q=0.8'
}

print("🔍 Téléchargement de la page...")
response = requests.get(SEARCH_URL, params=params, headers=headers, timeout=10)

if response.status_code != 200:
    print(f"❌ Erreur HTTP {response.status_code}")
    exit(1)

print("✅ Page téléchargée\n")

# Sauvegarde le HTML complet
with open('face_to_face_page.html', 'w', encoding='utf-8') as f:
    f.write(response.text)
print("💾 HTML sauvegardé dans 'face_to_face_page.html'\n")

# Parse avec BeautifulSoup
soup = BeautifulSoup(response.text, 'html.parser')

print("="*80)
print("ANALYSE DE LA STRUCTURE HTML")
print("="*80)

# 1. Cherche toutes les classes contenant "product"
print("\n📦 Éléments avec 'product' dans la classe :")
product_elems = soup.find_all(class_=re.compile(r'product', re.I))
print(f"   Trouvé : {len(product_elems)} éléments")
for i, elem in enumerate(product_elems[:5], 1):
    print(f"   {i}. <{elem.name}> class='{elem.get('class')}'")

# 2. Cherche les liens (probablement vers les cartes)
print("\n🔗 Liens trouvés :")
links = soup.find_all('a', href=re.compile(r'fable|mirror', re.I))
print(f"   Trouvé : {len(links)} liens avec 'fable' ou 'mirror'")
for i, link in enumerate(links[:5], 1):
    print(f"   {i}. {link.get('href')}")

# 3. Cherche les prix (format X.XX$ ou X,XX$)
print("\n💰 Texte contenant des prix :")
text = soup.get_text()
prices = re.findall(r'(\d+[.,]\d{2})\s*\$', text)
print(f"   Trouvé : {len(prices)} prix")
print(f"   Exemples : {prices[:10]}")

# 4. Cherche des éléments <li> ou <article>
print("\n📋 Éléments <li> :")
li_elems = soup.find_all('li')
print(f"   Trouvé : {len(li_elems)} éléments <li>")

print("\n📄 Éléments <article> :")
article_elems = soup.find_all('article')
print(f"   Trouvé : {len(article_elems)} éléments <article>")

# 5. Cherche les divs avec data-*
print("\n📊 Éléments avec attributs data-* :")
data_elems = soup.find_all(attrs={'data-product-id': True})
print(f"   data-product-id : {len(data_elems)} éléments")

data_elems = soup.find_all(attrs={'data-item': True})
print(f"   data-item : {len(data_elems)} éléments")

# 6. Affiche un échantillon du HTML autour du premier prix trouvé
print("\n" + "="*80)
print("ÉCHANTILLON HTML AUTOUR D'UN PRIX")
print("="*80)

if prices:
    first_price = prices[0]
    # Cherche ce prix dans le HTML
    index = response.text.find(first_price)
    if index != -1:
        start = max(0, index - 500)
        end = min(len(response.text), index + 500)
        sample = response.text[start:end]
        print(sample)

print("\n✅ Analyse terminée !")
print("📝 Ouvre 'face_to_face_page.html' dans ton navigateur pour inspecter la structure")