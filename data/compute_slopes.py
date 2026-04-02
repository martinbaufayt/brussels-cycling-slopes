"""
compute_slopes.py
-----------------
Calcule la pente de chaque tronçon cyclable de Bruxelles
en croisant les routes OSM avec le Modèle Numérique de Terrain (MNT).

Résultat : remplit la table "slopes" dans PostGIS.

Comment ça marche ?
  1. On lit chaque route de la table cycling_roads (PostGIS)
  2. On la reprojette en Lambert 72 (EPSG:31370) pour travailler en mètres
  3. On la découpe en petits segments de ~50m
  4. Pour chaque segment, on lit l'altitude au début et à la fin
     directement dans le fichier GeoTIFF (sans l'importer en base)
  5. On calcule : pente% = |dénivelé| / longueur × 100
  6. On insère les résultats dans la table slopes

Dépendances :
  pip install psycopg2-binary gdal pyproj shapely

Exécution :
  python3 data/compute_slopes.py
"""

import os
import math
import psycopg2
import psycopg2.extras
from osgeo import gdal, osr
from shapely.geometry import LineString, shape
from shapely.ops import transform
from pyproj import Transformer

# ── Configuration ─────────────────────────────────────────────────────────────

DB_CONFIG = {
    "host":     "localhost",
    "port":     5433,          # 5433 car 5432 est occupé par PostgreSQL local
    "dbname":   "gisdb",
    "user":     "gisuser",
    "password": "gispassword",
}

MNT_PATH      = "data/raw/BrusselsMNT_50cm.tif"
SEGMENT_LENGTH = 50    # longueur cible de chaque sous-segment, en mètres
MIN_SLOPE_PCT  = 0.0   # on stocke TOUTES les pentes (le filtre sera dans l'API)
BATCH_SIZE     = 500   # nombre d'insertions par transaction (performances)


# ── Étape 1 : ouvrir le MNT ───────────────────────────────────────────────────
#
# GDAL ouvre le fichier GeoTIFF et le garde en mémoire virtuelle.
# Il ne charge PAS tout le fichier — il lit seulement les pixels demandés.
# C'est pourquoi on peut travailler avec un fichier de 4.4 GB sans problème.

print("Ouverture du MNT...")
mnt = gdal.Open(MNT_PATH, gdal.GA_ReadOnly)

if mnt is None:
    raise FileNotFoundError(f"Impossible d'ouvrir {MNT_PATH}")

# Récupérer la "géotransformation" du raster.
# C'est une formule qui convertit (colonne, ligne) pixel → (X, Y) coordonnées.
# Format : (X_origine, taille_pixel_X, rotation_X, Y_origine, rotation_Y, taille_pixel_Y)
gt = mnt.GetGeoTransform()

# La bande 1 contient les valeurs d'altitude
band      = mnt.GetRasterBand(1)
nodata    = band.GetNoDataValue()   # valeur "pas de données" = -3.4e+38 dans notre cas

print(f"MNT ouvert : {mnt.RasterXSize}×{mnt.RasterYSize} pixels, résolution {gt[1]}m")


def get_altitude(x_lambert, y_lambert):
    """
    Lit l'altitude à une coordonnée Lambert 72 (EPSG:31370).

    Convertit la coordonnée géographique en indice de pixel,
    puis lit la valeur d'altitude dans le GeoTIFF.

    Retourne None si le pixel est hors du raster ou en zone NoData.
    """
    # Conversion coordonnée → pixel
    # Formule inverse de la géotransformation
    col = int((x_lambert - gt[0]) / gt[1])  # colonne pixel
    row = int((y_lambert - gt[3]) / gt[5])  # ligne pixel

    # Vérifier que le pixel est dans les limites du raster
    if col < 0 or row < 0 or col >= mnt.RasterXSize or row >= mnt.RasterYSize:
        return None

    # Lire un seul pixel : ReadAsArray(colonne, ligne, largeur, hauteur)
    value = band.ReadAsArray(col, row, 1, 1)

    if value is None:
        return None

    altitude = float(value[0][0])

    # Exclure les valeurs NoData
    if nodata is not None and abs(altitude - nodata) < 1:
        return None

    return altitude


def segmentize(linestring, max_length):
    """
    Découpe une LineString en segments de longueur maximale `max_length` mètres.

    Pourquoi découper ?
    Un tronçon OSM peut faire 500m de long avec un dénivelé variable.
    Si on ne calcule qu'une pente globale, on rate les variations locales.
    En découpant en segments de 50m, on capture les changements de pente
    tout le long de la route.

    Retourne une liste de LineString, chacune ≤ max_length mètres.
    """
    total_length = linestring.length
    if total_length <= max_length:
        return [linestring]

    segments = []
    coords   = list(linestring.coords)
    seg_start = coords[0]
    seg_coords = [seg_start]
    accumulated = 0.0

    for i in range(1, len(coords)):
        prev = coords[i - 1]
        curr = coords[i]
        step = math.sqrt((curr[0]-prev[0])**2 + (curr[1]-prev[1])**2)

        if accumulated + step >= max_length:
            # Ce pas dépasse la longueur cible → couper ici
            seg_coords.append(curr)
            if len(seg_coords) >= 2:
                segments.append(LineString(seg_coords))
            seg_coords = [curr]
            accumulated = 0.0
        else:
            seg_coords.append(curr)
            accumulated += step

    if len(seg_coords) >= 2:
        segments.append(LineString(seg_coords))

    return segments


# ── Étape 2 : connexion PostgreSQL ────────────────────────────────────────────
#
# psycopg2 est la bibliothèque Python standard pour parler à PostgreSQL.
# On utilise un "cursor" pour envoyer des requêtes SQL.

print("Connexion à PostgreSQL...")
conn = psycopg2.connect(**DB_CONFIG)
cur  = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# ── Étape 3 : transformer WGS84 → Lambert 72 ──────────────────────────────────
#
# Les routes OSM sont en WGS84 (latitude/longitude, EPSG:4326).
# Le MNT est en Lambert 72 (mètres, EPSG:31370).
# Pour échantillonner l'altitude, il faut travailler dans le même système.
#
# pyproj.Transformer gère la conversion mathématique entre les deux systèmes.
# always_xy=True : force l'ordre (longitude, latitude) plutôt que (lat, lon)
# — évite une source de confusion classique.

transformer_to_lambert = Transformer.from_crs(
    "EPSG:4326", "EPSG:31370", always_xy=True
)

def to_lambert(geom):
    """Reprojette une géométrie Shapely de WGS84 vers Lambert 72."""
    return transform(transformer_to_lambert.transform, geom)


# ── Étape 4 : lire les routes et calculer les pentes ─────────────────────────

print("Lecture des routes depuis PostGIS...")

cur.execute("""
    SELECT
        id,
        name,
        highway,
        surface,
        ST_AsText(geom) AS wkt    -- WKT = "Well-Known Text", représentation texte d'une géométrie
    FROM cycling_roads
    WHERE ST_IsValid(geom)        -- ignorer les géométries corrompues
    ORDER BY id
""")

roads = cur.fetchall()
print(f"{len(roads)} routes à traiter...")

# Préparer la requête d'insertion dans slopes
# Le %s est un placeholder psycopg2 (évite les injections SQL)
insert_sql = """
    INSERT INTO slopes (
        road_id, road_name, length_m,
        alt_start, alt_end, elevation_diff, slope_pct, slope_direction,
        highway, surface, geom
    ) VALUES (
        %s, %s, %s,
        %s, %s, %s, %s, %s,
        %s, %s,
        ST_GeomFromText(%s, 31370)   -- on insère en Lambert 72
    )
"""

inserted  = 0
skipped   = 0
batch     = []

cur_insert = conn.cursor()

for i, road in enumerate(roads):
    if i % 1000 == 0:
        print(f"  {i}/{len(roads)} routes traitées, {inserted} segments insérés...")

    try:
        # Reconstruire la géométrie Shapely depuis le WKT
        from shapely import wkt as shapely_wkt
        geom_wgs84 = shapely_wkt.loads(road["wkt"])

        # Reprojeter en Lambert 72 pour travailler en mètres
        geom_lambert = to_lambert(geom_wgs84)

        # Découper en segments de ~50m
        segments = segmentize(geom_lambert, SEGMENT_LENGTH)

        for seg in segments:
            coords = list(seg.coords)
            if len(coords) < 2:
                continue

            start = coords[0]   # (X, Y) en Lambert 72
            end   = coords[-1]

            # Lire l'altitude au début et à la fin du segment
            alt_start = get_altitude(start[0], start[1])
            alt_end   = get_altitude(end[0], end[1])

            # Si l'une des deux altitudes est manquante, on ignore ce segment
            if alt_start is None or alt_end is None:
                skipped += 1
                continue

            length_m = seg.length   # longueur en mètres (car on est en Lambert 72)

            if length_m < 5:        # ignorer les segments trop courts (bruit)
                skipped += 1
                continue

            elevation_diff = alt_end - alt_start
            slope_pct      = abs(elevation_diff) / length_m * 100
            direction      = "montée" if elevation_diff > 0 else "descente"

            # Convertir la géométrie Shapely en WKT pour l'insertion SQL
            seg_wkt = seg.wkt

            batch.append((
                road["id"],
                road["name"] or "",
                round(length_m, 2),
                round(alt_start, 3),
                round(alt_end, 3),
                round(elevation_diff, 3),
                round(slope_pct, 2),
                direction,
                road["highway"] or "",
                road["surface"] or "",
                seg_wkt,
            ))

            inserted += 1

            # Insérer par lots pour de meilleures performances
            if len(batch) >= BATCH_SIZE:
                cur_insert.executemany(insert_sql, batch)
                conn.commit()
                batch = []

    except Exception as e:
        print(f"  ⚠ Erreur sur route {road['id']} : {e}")
        continue

# Insérer le dernier lot restant
if batch:
    cur_insert.executemany(insert_sql, batch)
    conn.commit()

# ── Étape 5 : rapport final ───────────────────────────────────────────────────

cur.execute("SELECT COUNT(*) AS n FROM slopes")
total = cur.fetchone()["n"]

cur.execute("SELECT COUNT(*) AS n FROM slopes WHERE slope_pct >= 4")
steep = cur.fetchone()["n"]

cur.execute("SELECT MAX(slope_pct) AS m FROM slopes")
max_slope = cur.fetchone()["m"]

print("\n═══════════════════════════════════════════")
print(" Calcul des pentes terminé")
print("═══════════════════════════════════════════")
print(f" Segments insérés    : {total}")
print(f" Segments ignorés    : {skipped} (NoData ou trop courts)")
print(f" Pentes ≥ 4%         : {steep}")
print(f" Pente maximale      : {max_slope:.1f}%")
print("")

# Fermeture propre
cur.close()
cur_insert.close()
conn.close()
mnt = None   # libère le fichier GeoTIFF
