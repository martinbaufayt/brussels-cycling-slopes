"""
db.py — Connexion à PostgreSQL/PostGIS
---------------------------------------
Ce module fournit une seule fonction : get_connection().
Tous les routers l'importent pour obtenir une connexion à la base.

Pourquoi ne pas créer la connexion directement dans chaque router ?
  → Centraliser la config évite la duplication.
  → Si on change de base de données ou d'URL, on modifie un seul fichier.

Pourquoi ne pas utiliser un ORM (SQLAlchemy) ?
  → Pour un projet pédagogique GIS, écrire du SQL brut est plus clair.
  → Les fonctions PostGIS (ST_AsGeoJSON, ST_Transform…) sont difficiles
    à exprimer proprement via un ORM.
"""

import os
import psycopg2
import psycopg2.extras  # pour RealDictCursor : résultats sous forme de dict

# L'URL de connexion est lue depuis une variable d'environnement.
# - En local      : définie dans le .env (localhost:5433)
# - En Docker     : définie dans docker-compose.yml (postgis:5432)
# C'est le même code, deux environnements différents.
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://gisuser:gispassword@localhost:5433/gisdb"  # valeur par défaut (dev local)
)


def get_connection():
    """
    Ouvre et retourne une connexion PostgreSQL.

    Utilisation dans un router :
        conn = get_connection()
        try:
            cur = conn.cursor()
            cur.execute("SELECT ...")
            rows = cur.fetchall()
        finally:
            conn.close()   # toujours fermer, même en cas d'erreur

    RealDictCursor : chaque ligne retournée est un dict Python {"colonne": valeur}
    au lieu d'un tuple (valeur1, valeur2, ...). Beaucoup plus lisible.
    """
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor
    )
