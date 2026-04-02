"""
download_osm_brussels.py
------------------------
Télécharge toutes les routes praticables à vélo sur la Région de
Bruxelles-Capitale via l'Overpass API (OpenStreetMap).

Résultat : data/raw/brussels_cycling_roads.geojson

Pourquoi Overpass et pas un téléchargement complet ?
  → On cible exactement notre zone et nos types de routes.
  → Résultat ~5 MB au lieu de ~120 MB pour toute la Belgique.

Exécution :
  python3 data/download_osm_brussels.py
"""

import json
import urllib.request
import urllib.parse

# ── 1. Bounding box de la Région de Bruxelles-Capitale ──────────────────────
# Format Overpass : (sud, ouest, nord, est)
# Ces coordonnées encadrent exactement les 19 communes bruxelloises.
BBOX = (50.7506, 4.2488, 50.9210, 4.5317)

# ── 2. Requête Overpass QL ───────────────────────────────────────────────────
#
# Overpass QL fonctionne comme du SQL pour OSM.
# On demande des "way" (lignes = routes) selon leurs tags OSM.
#
# Tags OSM pour les routes cyclables :
#   highway=cycleway        → piste cyclable dédiée
#   highway=path/track      → chemin/sentier accessible au vélo
#   highway=residential     → rue de quartier (vélos autorisés par défaut)
#   highway=living_street   → zone de rencontre
#   highway=tertiary/secondary/primary → voiries plus larges mais praticables
#   highway=unclassified    → petite route sans classification
#   highway=footway/pedestrian + bicycle=yes/designated → chemin piéton partagé
#
#   bicycle=no              → exclu explicitement (rue où le vélo est interdit)
#
# [out:json]    → format de sortie JSON (on convertira en GeoJSON ensuite)
# [timeout:90]  → max 90s de traitement côté serveur
# [bbox:...]    → limite géographique, plus efficace que de filtrer après
# out geom;     → inclut les coordonnées géométriques dans la réponse

QUERY = f"""
[out:json][timeout:90][bbox:{BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}];
(
  way["highway"~"^(cycleway|path|track|residential|living_street|tertiary|secondary|primary|unclassified|service)$"]["bicycle"!="no"];
  way["highway"~"^(footway|pedestrian)$"]["bicycle"~"^(yes|designated|permissive)$"];
);
out geom;
"""

# ── 3. Envoi de la requête ───────────────────────────────────────────────────
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

print("Envoi de la requête Overpass API...")
print(f"Zone : bbox={BBOX}")

data = urllib.parse.urlencode({"data": QUERY}).encode()
req  = urllib.request.Request(OVERPASS_URL, data=data)
req.add_header("User-Agent", "gis-opensource-project1/1.0")

with urllib.request.urlopen(req, timeout=120) as response:
    raw = response.read()

osm = json.loads(raw)
print(f"Réponse reçue : {len(osm['elements'])} éléments OSM")

# ── 4. Conversion OSM JSON → GeoJSON ────────────────────────────────────────
#
# OSM retourne ses propres objets "way" avec des "geometry" (liste de nodes).
# GeoJSON est le format standard pour les données géospatiales sur le web :
#   { "type": "Feature", "geometry": {...}, "properties": {...} }
# C'est ce format que PostGIS, Leaflet, et notre API FastAPI comprennent.

features = []

for element in osm["elements"]:
    if element["type"] != "way":
        continue

    # Chaque "way" OSM a une liste de points (geometry)
    coords = [
        [node["lon"], node["lat"]]   # GeoJSON utilise [longitude, latitude]
        for node in element.get("geometry", [])
    ]

    if len(coords) < 2:              # ignorer les ways sans géométrie valide
        continue

    # Les "tags" OSM contiennent toutes les métadonnées de la route
    tags = element.get("tags", {})

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": coords
        },
        "properties": {
            "osm_id":      element["id"],
            "name":        tags.get("name", ""),          # nom de la rue
            "highway":     tags.get("highway", ""),       # type de voie
            "bicycle":     tags.get("bicycle", ""),       # tag vélo explicite
            "cycleway":    tags.get("cycleway", ""),      # aménagement cyclable
            "surface":     tags.get("surface", ""),       # revêtement (asphalt, cobblestone…)
            "maxspeed":    tags.get("maxspeed", ""),      # vitesse max
            "oneway":      tags.get("oneway", ""),        # sens unique
            "oneway_bicycle": tags.get("oneway:bicycle", ""),  # sens unique sauf vélos
        }
    }
    features.append(feature)

geojson = {
    "type": "FeatureCollection",
    "features": features
}

# ── 5. Sauvegarde ────────────────────────────────────────────────────────────
output_path = "data/raw/brussels_cycling_roads.geojson"

with open(output_path, "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False)

size_mb = len(raw) / 1e6
print(f"\nFichier sauvegardé : {output_path}")
print(f"Taille réponse OSM : {size_mb:.1f} MB")
print(f"Nombre de tronçons : {len(features)}")
print("\nColonnes disponibles :")
print("  osm_id, name, highway, bicycle, cycleway, surface, maxspeed, oneway")
