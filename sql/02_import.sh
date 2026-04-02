#!/bin/bash
# =============================================================================
# 02_import.sh
# Import des données dans PostGIS
#
# Ce script fait deux choses :
#   1. Importe les routes cyclables OSM (GeoJSON) dans la table cycling_roads
#   2. Appelle le script Python qui calcule les pentes et remplit la table slopes
#
# Prérequis :
#   - PostGIS doit tourner (docker-compose up -d postgis)
#   - GDAL installé (brew install gdal)
#   - Python + dépendances installés (pip install -r backend/requirements.txt)
#
# Usage :
#   bash sql/02_import.sh
# =============================================================================

set -e  # arrête le script si une commande échoue

# ── Paramètres de connexion ────────────────────────────────────────────────────
# Ces variables correspondent à ce qu'on a défini dans docker-compose.yml
DB_HOST="localhost"
DB_PORT="5433"          # 5433 car 5432 est occupé par PostgreSQL local
DB_NAME="gisdb"
DB_USER="gisuser"
DB_PASS="gispassword"

# La "connection string" PG est le format standard pour se connecter à PostgreSQL.
# ogr2ogr, psql, et Python l'utilisent tous.
PG_CONN="PG:host=${DB_HOST} port=${DB_PORT} dbname=${DB_NAME} user=${DB_USER} password=${DB_PASS}"

echo "═══════════════════════════════════════════"
echo " Import des données dans PostGIS"
echo "═══════════════════════════════════════════"

# ── Étape 1 : vérifier que PostGIS est accessible ─────────────────────────────
echo ""
echo "▶ Vérification de la connexion PostGIS..."

PGPASSWORD=${DB_PASS} psql \
    -h ${DB_HOST} -p ${DB_PORT} \
    -U ${DB_USER} -d ${DB_NAME} \
    -c "SELECT PostGIS_Version();" \
    > /dev/null 2>&1 || {
    echo "✗ Impossible de se connecter à PostGIS."
    echo "  Lance d'abord : docker-compose up -d postgis"
    echo "  Puis attends ~10 secondes et relance ce script."
    exit 1
}

echo "✓ PostGIS accessible."

# ── Étape 2 : import des routes cyclables ────────────────────────────────────
#
# ogr2ogr : l'outil universel de conversion géospatiale (fait partie de GDAL/OGR)
#
# Décomposition de la commande :
#
#   ogr2ogr
#     -f "PostgreSQL"              → format de sortie : PostgreSQL/PostGIS
#     "${PG_CONN}"                 → où écrire (notre base de données)
#     "data/raw/brussels_cycling_roads.geojson"  → fichier source
#     -nln "cycling_roads"         → nln = "new layer name" = nom de la table destination
#     -nlt LINESTRING              → nlt = "new layer type" = force le type géométrique
#     -lco GEOMETRY_NAME=geom      → lco = "layer creation option" = nom de la colonne géo
#     -lco FID=id                  → nom de la colonne identifiant
#     -overwrite                   → écrase la table si elle existe déjà
#     -progress                    → affiche une barre de progression
#
# Note sur la projection :
#   Le GeoJSON est en WGS84 (EPSG:4326), notre table cycling_roads attend EPSG:4326.
#   On ne reprojette PAS ici — on garde le WGS84 pour la table brute.
#   La reprojection en Lambert 72 se fera lors du calcul des pentes (script Python).

echo ""
echo "▶ Import des routes cyclables OSM → table cycling_roads..."

PGPASSWORD=${DB_PASS} ogr2ogr \
    -f "PostgreSQL" \
    "${PG_CONN}" \
    "data/raw/brussels_cycling_roads.geojson" \
    -nln "cycling_roads" \
    -nlt LINESTRING \
    -lco GEOMETRY_NAME=geom \
    -lco FID=id \
    -overwrite \
    -progress

echo "✓ Routes importées."

# Vérification rapide : combien de lignes dans la table ?
COUNT=$(PGPASSWORD=${DB_PASS} psql \
    -h ${DB_HOST} -p ${DB_PORT} \
    -U ${DB_USER} -d ${DB_NAME} \
    -t -c "SELECT COUNT(*) FROM cycling_roads;")

echo "  → ${COUNT// /} tronçons dans la base."

# ── Étape 3 : calcul des pentes ───────────────────────────────────────────────
#
# Cette étape est la plus importante.
# Un script Python va :
#   - lire chaque tronçon de cycling_roads
#   - le découper en segments de ~50m
#   - échantillonner l'altitude au début et à la fin de chaque segment
#     en lisant le fichier GeoTIFF BrusselsMNT_50cm.tif
#   - calculer la pente en %
#   - insérer les résultats dans la table slopes

echo ""
echo "▶ Calcul des pentes (lecture MNT + insertion dans slopes)..."
echo "  Cette étape peut prendre plusieurs minutes."

python3 data/compute_slopes.py

echo "✓ Pentes calculées."

# Vérification finale
SLOPE_COUNT=$(PGPASSWORD=${DB_PASS} psql \
    -h ${DB_HOST} -p ${DB_PORT} \
    -U ${DB_USER} -d ${DB_NAME} \
    -t -c "SELECT COUNT(*) FROM slopes;")

STEEP_COUNT=$(PGPASSWORD=${DB_PASS} psql \
    -h ${DB_HOST} -p ${DB_PORT} \
    -U ${DB_USER} -d ${DB_NAME} \
    -t -c "SELECT COUNT(*) FROM slopes WHERE slope_pct >= 4;")

echo ""
echo "═══════════════════════════════════════════"
echo " Import terminé"
echo "═══════════════════════════════════════════"
echo " Segments totaux    : ${SLOPE_COUNT// /}"
echo " Pentes ≥ 4%        : ${STEEP_COUNT// /}"
echo ""
