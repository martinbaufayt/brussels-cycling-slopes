# Brussels Cycling Slopes

Application web GIS open-source pour visualiser et explorer les pentes cyclables de la Région de Bruxelles-Capitale.

Projet portfolio construit pour apprendre la stack SDI open-source — une alternative 100 % libre à ArcGIS Pro + ArcGIS Server.

---

## Aperçu

- **58 845 tronçons** du réseau cyclable bruxellois (OpenStreetMap)
- **64 875 segments de pente d'une longueur de 50m** calculés à partir du MNT LiDAR à 0,5 m de résolution
- Visualisation interactive par niveau de difficulté (léger / modéré / difficile / très difficile)
- Widget checklist pour suivre les pentes déjà parcourues

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                         Navigateur                           │
│                    Leaflet.js (frontend)                     │
└──────────┬──────────────────────────┬────────────────────────┘
           │ WMS (tuiles PNG)          │ GeoJSON interactif
           ▼                           ▼
┌─────────────────────┐     ┌──────────────────────┐
│     GeoServer       │     │    FastAPI backend    │
│    (port 8080)      │     │     (port 8000)       │
│                     │     │                       │
│  Couches WMS/WFS    │     │  /slopes/geojson      │
│  Style SLD          │     │  /checklist           │
└──────────┬──────────┘     └──────────┬────────────┘
           │                           │
           └─────────────┬─────────────┘
                         ▼
              ┌─────────────────────┐
              │  PostgreSQL 16      │
              │     + PostGIS 3.4   │
              │    (port 5433)      │
              │                     │
              │  - cycling_roads    │
              │  - slopes           │
              │  - checklist        │
              └─────────────────────┘
```

---

## Stack technique

| Couche     | Technologie                  | Rôle                                          |
|------------|------------------------------|-----------------------------------------------|
| Base de données | PostgreSQL 16 + PostGIS 3.4 | Stockage et requêtes spatiales           |
| Serveur carto   | GeoServer 2.25.2        | Publication des couches OGC WMS               |
| Backend    | FastAPI (Python 3.12)        | API REST — GeoJSON filtré + checklist         |
| Frontend   | Leaflet.js 1.9.4             | Carte interactive dans le navigateur          |
| DevOps     | Docker + docker-compose      | Environnement reproductible en une commande   |

---

## Structure du projet

```
brussels-cycling-slopes/
├── backend/                  # API FastAPI
│   ├── app/
│   │   ├── main.py           # Point d'entrée, CORS
│   │   ├── routers/
│   │   │   ├── slopes.py     # GET /slopes, /slopes/geojson, /slopes/{id}
│   │   │   └── checklist.py  # GET/POST/DELETE /checklist
│   │   └── services/
│   │       └── db.py         # Connexion psycopg2 + RealDictCursor
│   ├── Dockerfile
│   └── requirements.txt
├── data/
│   ├── download_osm_brussels.py   # Télécharge le réseau cyclable via Overpass API
│   ├── compute_slopes.py          # Calcule les pentes depuis le MNT LiDAR
│   ├── raw/                       # Données sources (non versionnées — voir ci-dessous)
│   └── processed/                 # Données intermédiaires
├── docker/
│   └── slopes_style.sld      # Style SLD pour GeoServer (symbologie par difficulté)
├── frontend/
│   ├── index.html
│   ├── css/style.css
│   └── js/map.js             # Leaflet : basemaps, WMS, GeoJSON, filtres, checklist
├── sql/
│   └── 01_schema.sql         # Schéma PostGIS : tables, index GIST, GENERATED COLUMN
├── docker-compose.yml
└── README.md
```

---

## Démarrage rapide

### Prérequis

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installé et lancé
- Git

### 1. Cloner le repo

```bash
git clone <your-repo-url>
cd brussels-cycling-slopes
```

### 2. Ajouter les données brutes

Les fichiers de données sont trop lourds pour Git et ne sont pas versionnés.

**Modèle numérique de terrain LiDAR 50cm - Lambert Belge 1972 (Fichier TIFF, ~4.4 GB)**

Disponible sur ([https://www.datastore.brussels.be](https://datastore.brussels/web/data/dataset/1d7bd49d-fe83-4388-af85-6f5dc8ec7909#access)). Données fournies par Paradigm.

À placer dans `data/raw/BrusselsMNT_50cm.tif`.

**Réseau cyclable OSM (généré automatiquement)**
```bash
python3 data/download_osm_brussels.py
# → crée data/raw/brussels_cycling_roads.geojson
```

### 3. Lancer toute la stack

```bash
docker compose up --build
```

La première fois : téléchargement des images Docker (~2 GB), construction du backend.
Les démarrages suivants : `docker compose up` suffit.

### 4. Importer les données dans PostGIS

```bash
# Importer le réseau cyclable OSM
ogr2ogr -f "PostgreSQL" \
  PG:"host=localhost port=5433 dbname=gisdb user=gisuser password=gispassword" \
  data/raw/brussels_cycling_roads.geojson \
  -nln cycling_roads -overwrite

# Calculer les pentes
python3 data/compute_slopes.py
```

### 5. Configurer GeoServer

Ouvrir http://localhost:8080/geoserver (admin / geoserver) et configurer :

1. **Workspace** : `cycling_brussels`
2. **Datastore PostGIS** : host=`postgis`, port=`5432`, db=`gisdb`, user=`gisuser`
3. **Couches** : publier `slopes` et `cycling_roads`
4. **Style SLD** : importer `docker/slopes_style.sld` et l'assigner à la couche `slopes`

### 6. Ouvrir le frontend

Ouvrir `frontend/index.html` dans le navigateur.

---

## Services

| Service   | URL                             | Credentials         |
|-----------|---------------------------------|---------------------|
| Frontend  | `frontend/index.html`           | —                   |
| API REST  | http://localhost:8000/docs      | —                   |
| GeoServer | http://localhost:8080/geoserver | admin / geoserver   |
| PostGIS   | localhost:**5433**              | gisuser / gispassword |

> Le port PostGIS est **5433** (pas 5432) pour éviter le conflit avec une installation locale de PostgreSQL.

---

## API endpoints

| Méthode | Chemin                  | Description                                      |
|---------|-------------------------|--------------------------------------------------|
| GET     | `/`                     | Health check                                     |
| GET     | `/slopes`               | Liste des pentes (filtres : difficulty, min_slope, max_slope, min_length) |
| GET     | `/slopes/geojson`       | GeoJSON pour Leaflet (mêmes filtres)             |
| GET     | `/slopes/{id}`          | Détail d'une pente                               |
| GET     | `/checklist`            | Pentes cochées par l'utilisateur                 |
| POST    | `/checklist/{slope_id}` | Cocher une pente                                 |
| DELETE  | `/checklist/{slope_id}` | Décocher une pente                               |

---

## Données

| Donnée | Source | Licence |
|--------|--------|---------|
| Réseau cyclable | OpenStreetMap via Overpass API | ODbL |
| MNT LiDAR 0.5m | Bruxelles-Capitale (UrbIS/Paradigm) | CC-0 |
| Basemap photo aérienne | UrbIS Ortho 2024 (WMTS) | CC-0 |
| Basemap CartoDB Positron| CartoDB Positron - OpenStreetMap Contributors  CC-0 |

---

## Objectifs pédagogiques

- Comprendre le développement full-stack d'une application web GIS en utilisant des technologies open-source
- Maîtriser les fonctions PostGIS : `ST_AsGeoJSON`, `ST_Transform`, `ST_Buffer`, index GIST
- Utiliser GeoServer pour publier des couches OGC WMS avec style SLD
- Construire une API REST qui retourne du GeoJSON avec FastAPI
- Conteneuriser une stack multi-services avec Docker Compose

---

## Licence

MIT — libre d'utilisation, modification et redistribution.
