-- =============================================================================
-- 01_schema.sql
-- Création du schéma de la base de données PostGIS
--
-- Ce script est exécuté automatiquement au premier démarrage du conteneur
-- PostGIS, car il est monté dans /docker-entrypoint-initdb.d/
-- =============================================================================

-- -----------------------------------------------------------------------------
-- Étape 1 : activer l'extension PostGIS
--
-- PostgreSQL de base ne connaît pas la géographie. PostGIS est une extension
-- qui ajoute :
--   - le type de colonne "geometry" (pour stocker des formes géo)
--   - des centaines de fonctions spatiales : ST_Buffer, ST_Intersects, etc.
--   - la gestion des systèmes de coordonnées (EPSG codes)
--
-- Sans cette ligne, toutes les commandes géospatiales échoueraient.
-- -----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_raster; -- pour importer le MNT plus tard

-- -----------------------------------------------------------------------------
-- Étape 2 : table "cycling_roads"
--
-- Stocke les tronçons de routes praticables à vélo, tels qu'ils viennent
-- d'OpenStreetMap. C'est la donnée brute, non traitée.
--
-- Chaque ligne = un segment de rue (une portion entre deux intersections).
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS cycling_roads (
    id          SERIAL PRIMARY KEY,     -- identifiant unique auto-incrémenté

    -- Métadonnées OpenStreetMap
    osm_id      BIGINT,                 -- l'ID OSM original (utile pour les mises à jour)
    name        TEXT,                   -- nom de la rue ("Avenue Louise", "Rue de la Loi"…)
    highway     TEXT,                   -- type de voie OSM ("cycleway", "residential", "tertiary"…)
    bicycle     TEXT,                   -- tag vélo explicite ("yes", "no", "designated"…)
    cycleway    TEXT,                   -- aménagement cyclable ("lane", "track", "shared"…)
    surface     TEXT,                   -- revêtement ("asphalt", "cobblestone", "gravel"…)
    maxspeed    TEXT,                   -- vitesse max en km/h (TEXT car parfois "walk", "30"…)
    oneway      TEXT,                   -- sens unique pour les voitures ("yes", "no", "-1"…)
    oneway_bicycle TEXT,                -- sens unique pour vélos (peut être différent voitures)

    -- Colonne géométrique
    -- Type : LineString = une ligne composée de plusieurs points
    -- SRID 4326 = WGS84 = le système GPS mondial (latitude/longitude)
    -- Le GeoJSON OSM est toujours en WGS84, on le stocke tel quel ici.
    geom        GEOMETRY(LineString, 4326)
);

-- Index spatial sur la géométrie
-- Sans cet index, une requête "trouve-moi toutes les routes dans ce rectangle"
-- lirait toute la table ligne par ligne — très lent sur 58 000 tronçons.
-- L'index GIST est l'index spatial standard de PostGIS.
CREATE INDEX IF NOT EXISTS idx_cycling_roads_geom
    ON cycling_roads USING GIST (geom);

-- Index sur osm_id pour les jointures et mises à jour futures
CREATE INDEX IF NOT EXISTS idx_cycling_roads_osm_id
    ON cycling_roads (osm_id);


-- -----------------------------------------------------------------------------
-- Étape 3 : table "slopes"
--
-- C'est notre table principale — le résultat du croisement entre
-- les routes OSM et le MNT (modèle numérique de terrain).
--
-- Elle ne sera PAS remplie par l'import SQL, mais par notre script Python
-- qui calcule les pentes tronçon par tronçon.
--
-- Chaque ligne = un micro-segment de ~50m avec sa pente calculée.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS slopes (
    id              SERIAL PRIMARY KEY,

    -- Référence vers la route parente (jointure avec cycling_roads)
    road_id         INTEGER REFERENCES cycling_roads(id) ON DELETE CASCADE,
    road_name       TEXT,               -- copié ici pour éviter des jointures à chaque requête

    -- Métriques de pente
    -- Ces valeurs seront calculées par le script Python
    length_m        FLOAT,              -- longueur du segment en mètres
    alt_start       FLOAT,              -- altitude au début du segment (en mètres)
    alt_end         FLOAT,              -- altitude à la fin du segment (en mètres)
    elevation_diff  FLOAT,              -- dénivelé = alt_end - alt_start (positif = montée)
    slope_pct       FLOAT,              -- pente en % = |dénivelé| / longueur × 100
    slope_direction TEXT,               -- "montée" ou "descente" (selon le sens de la géométrie OSM)

    -- Classe de difficulté — colonne générée automatiquement depuis slope_pct
    -- GENERATED ALWAYS AS ... STORED : calculée et stockée automatiquement,
    -- jamais désynchronisée avec slope_pct, non modifiable manuellement.
    -- Utilisée pour la symbologie par catégorie dans Leaflet / GeoServer.
    difficulty      TEXT GENERATED ALWAYS AS (
        CASE
            WHEN slope_pct > 25  THEN 'artefact'
            WHEN slope_pct >= 12 THEN 'tres_difficile'
            WHEN slope_pct >= 8  THEN 'difficile'
            WHEN slope_pct >= 4  THEN 'modere'
            WHEN slope_pct >= 2  THEN 'leger'
            ELSE                      'plat'
        END
    ) STORED,

    -- Infos complémentaires utiles pour l'appli vélo
    highway         TEXT,               -- type de voie (copié de cycling_roads)
    surface         TEXT,               -- revêtement (copié de cycling_roads)

    -- Colonne géométrique
    -- SRID 31370 = Lambert 72 belge (unités en mètres)
    -- On travaille en Lambert 72 pour les calculs de distance/pente
    -- car ST_Length() en WGS84 retourne des degrés, pas des mètres.
    geom            GEOMETRY(LineString, 31370),

    -- Timestamp de calcul (utile pour savoir si les données sont à jour)
    computed_at     TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_slopes_geom
    ON slopes USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_slopes_slope_pct
    ON slopes (slope_pct);              -- pour filtrer rapidement "pente > 4%"

CREATE INDEX IF NOT EXISTS idx_slopes_difficulty
    ON slopes (difficulty);             -- pour filtrer par classe (modere, difficile…)

CREATE INDEX IF NOT EXISTS idx_slopes_road_id
    ON slopes (road_id);


-- -----------------------------------------------------------------------------
-- Étape 4 : table "checklist"
--
-- Le widget de l'application — l'utilisateur coche les pentes qu'il a faites.
-- Simple table de suivi, sans géométrie.
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS checklist (
    id          SERIAL PRIMARY KEY,
    slope_id    INTEGER REFERENCES slopes(id) ON DELETE CASCADE UNIQUE, -- une entrée max par pente
    done        BOOLEAN DEFAULT FALSE,  -- coché ou non
    done_at     TIMESTAMP,              -- date à laquelle la pente a été faite
    note        TEXT                    -- commentaire libre de l'utilisateur
);


-- -----------------------------------------------------------------------------
-- Confirmation
-- -----------------------------------------------------------------------------
DO $$
BEGIN
    RAISE NOTICE 'Schéma créé avec succès : cycling_roads, slopes, checklist';
END $$;
