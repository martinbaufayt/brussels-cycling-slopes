"""
slopes.py — Endpoints pour les pentes cyclables
-------------------------------------------------
GET /slopes           → liste filtrée de pentes (JSON)
GET /slopes/geojson   → toutes les pentes en GeoJSON (pour Leaflet)
GET /slopes/{id}      → une pente précise en GeoJSON
"""

from fastapi import APIRouter, HTTPException, Query
from app.services.db import get_connection

router = APIRouter(prefix="/slopes", tags=["slopes"])


# ── GET /slopes ───────────────────────────────────────────────────────────────
#
# Retourne une liste de pentes selon des filtres optionnels.
# Exemple : GET /slopes?difficulty=difficile&min_slope=8&limit=50
#
# Query parameters (tous optionnels) :
#   difficulty  → filtre sur la classe ('modere', 'difficile', 'tres_difficile')
#   min_slope   → pente minimale en %
#   max_slope   → pente maximale en % (défaut 25 pour exclure les artefacts)
#   min_length  → longueur minimale du segment en mètres
#   limit       → nombre maximum de résultats (défaut 200)
#
# On exclut toujours les 'artefact' (pente > 25%) sauf demande explicite.

@router.get("")
def list_slopes(
    difficulty: str  | None = Query(None, description="Classe de difficulté"),
    min_slope:  float       = Query(4.0,  description="Pente minimale en %"),
    max_slope:  float       = Query(25.0, description="Pente maximale en %"),
    min_length: float       = Query(30.0, description="Longueur minimale en mètres"),
    limit:      int         = Query(200,  description="Nombre max de résultats", le=1000),
):
    conn = get_connection()
    try:
        cur = conn.cursor()

        # On construit la requête avec des paramètres (%s) pour éviter
        # toute injection SQL — jamais interpoler des valeurs utilisateur
        # directement dans une chaîne SQL.
        query = """
            SELECT
                id,
                road_name,
                highway,
                surface,
                ROUND(length_m::numeric, 1)       AS length_m,
                ROUND(alt_start::numeric, 1)      AS alt_start,
                ROUND(alt_end::numeric, 1)        AS alt_end,
                ROUND(elevation_diff::numeric, 1) AS elevation_diff,
                ROUND(slope_pct::numeric, 2)      AS slope_pct,
                slope_direction,
                difficulty
            FROM slopes
            WHERE slope_pct BETWEEN %s AND %s
              AND length_m >= %s
        """
        params = [min_slope, max_slope, min_length]

        if difficulty:
            query += " AND difficulty = %s"
            params.append(difficulty)

        query += " ORDER BY slope_pct DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()

        return {
            "count": len(rows),
            "filters": {
                "difficulty": difficulty,
                "min_slope": min_slope,
                "max_slope": max_slope,
                "min_length": min_length,
            },
            "slopes": [dict(r) for r in rows]
        }
    finally:
        conn.close()


# ── GET /slopes/geojson ───────────────────────────────────────────────────────
#
# Retourne un GeoJSON FeatureCollection — le format que Leaflet comprend nativement.
#
# ST_AsGeoJSON(ST_Transform(geom, 4326)) :
#   - ST_Transform(geom, 4326) : reprojette Lambert 72 → WGS84
#     (Leaflet travaille en WGS84 / latitude-longitude)
#   - ST_AsGeoJSON(...)        : convertit la géométrie en JSON texte
#
# On ne retourne que les pentes "intéressantes" (≥ 4%, ≤ 25%, ≥ 30m)
# pour ne pas surcharger le frontend avec 64 000 segments.

@router.get("/geojson")
def slopes_geojson(
    difficulty: str  | None = Query(None),
    min_slope:  float       = Query(4.0),
    max_slope:  float       = Query(25.0),
    min_length: float       = Query(30.0),
):
    conn = get_connection()
    try:
        cur = conn.cursor()

        query = """
            SELECT
                id,
                road_name,
                highway,
                surface,
                ROUND(length_m::numeric, 1)      AS length_m,
                ROUND(slope_pct::numeric, 2)     AS slope_pct,
                ROUND(elevation_diff::numeric,1) AS elevation_diff,
                slope_direction,
                difficulty,
                ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geometry
            FROM slopes
            WHERE slope_pct BETWEEN %s AND %s
              AND length_m >= %s
        """
        params = [min_slope, max_slope, min_length]

        if difficulty:
            query += " AND difficulty = %s"
            params.append(difficulty)

        cur.execute(query, params)
        rows = cur.fetchall()

        # Construction manuelle du GeoJSON FeatureCollection.
        # FastAPI retourne ce dict comme du JSON automatiquement.
        import json
        features = [
            {
                "type": "Feature",
                "geometry": json.loads(row["geometry"]),
                "properties": {
                    "id":             row["id"],
                    "road_name":      row["road_name"],
                    "highway":        row["highway"],
                    "surface":        row["surface"],
                    "length_m":       row["length_m"],
                    "slope_pct":      row["slope_pct"],
                    "elevation_diff": row["elevation_diff"],
                    "direction":      row["slope_direction"],
                    "difficulty":     row["difficulty"],
                }
            }
            for row in rows
        ]

        return {
            "type": "FeatureCollection",
            "features": features
        }
    finally:
        conn.close()


# ── GET /slopes/{id} ──────────────────────────────────────────────────────────
#
# Retourne une seule pente par son ID, en GeoJSON.
# Utile quand l'utilisateur clique sur un segment dans la carte.

@router.get("/{slope_id}")
def get_slope(slope_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                id, road_name, highway, surface,
                ROUND(length_m::numeric, 1)      AS length_m,
                ROUND(alt_start::numeric, 1)     AS alt_start,
                ROUND(alt_end::numeric, 1)       AS alt_end,
                ROUND(elevation_diff::numeric,1) AS elevation_diff,
                ROUND(slope_pct::numeric, 2)     AS slope_pct,
                slope_direction,
                difficulty,
                ST_AsGeoJSON(ST_Transform(geom, 4326)) AS geometry
            FROM slopes
            WHERE id = %s
        """, [slope_id])

        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Pente {slope_id} introuvable")

        import json
        return {
            "type": "Feature",
            "geometry": json.loads(row["geometry"]),
            "properties": {k: v for k, v in row.items() if k != "geometry"}
        }
    finally:
        conn.close()
