"""
main.py — Point d'entrée de l'API FastAPI
------------------------------------------
C'est ici que l'application est créée et que les routers sont branchés.

FastAPI est un framework Python moderne qui génère automatiquement :
  - La documentation interactive (Swagger UI) sur /docs
  - La validation des paramètres d'entrée (via Pydantic)
  - Les réponses JSON
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import slopes, checklist

# ── Création de l'application ─────────────────────────────────────────────────
app = FastAPI(
    title="Brussels Cycling Slopes API",
    description="API pour explorer les pentes cyclables de Bruxelles.",
    version="1.0.0",
)

# ── CORS (Cross-Origin Resource Sharing) ─────────────────────────────────────
#
# Sans ce middleware, le navigateur bloquerait les requêtes du frontend
# vers l'API car ils tournent sur des ports différents (8000 vs fichier local).
# En développement on autorise tout ("*"). En production on restreindrait
# à l'URL exacte du frontend.

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Branchement des routers ───────────────────────────────────────────────────
#
# Chaque router gère un groupe d'endpoints.
# Le préfixe est déjà défini dans chaque router (/slopes, /checklist).

app.include_router(slopes.router)
app.include_router(checklist.router)


# ── Health check ──────────────────────────────────────────────────────────────
#
# Endpoint minimal pour vérifier que l'API tourne.
# Utilisé aussi par Docker pour les healthchecks.

@app.get("/", tags=["health"])
def root():
    return {"status": "ok", "message": "Brussels Cycling Slopes API"}
