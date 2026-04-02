"""
checklist.py — Endpoints pour le widget de suivi des pentes
------------------------------------------------------------
GET  /checklist              → liste toutes les pentes cochées
POST /checklist/{slope_id}   → marquer une pente comme faite
DELETE /checklist/{slope_id} → décocher une pente
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.db import get_connection

router = APIRouter(prefix="/checklist", tags=["checklist"])


# Pydantic valide automatiquement le corps JSON des requêtes POST.
# Si "note" est absent du JSON, il prend la valeur None (optionnel).
class ChecklistEntry(BaseModel):
    note: str | None = None   # commentaire libre ("Fait par vent de face !")


# ── GET /checklist ────────────────────────────────────────────────────────────
#
# Retourne toutes les pentes cochées, avec les infos de la pente jointe.
# On fait une JOIN avec la table slopes pour récupérer le nom et la pente%.

@router.get("")
def get_checklist():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute("""
            SELECT
                c.id,
                c.slope_id,
                s.road_name,
                ROUND(s.slope_pct::numeric, 2) AS slope_pct,
                s.difficulty,
                s.slope_direction,
                c.done,
                c.done_at,
                c.note
            FROM checklist c
            JOIN slopes s ON s.id = c.slope_id
            ORDER BY c.done_at DESC NULLS LAST
        """)
        rows = cur.fetchall()
        return {"count": len(rows), "entries": [dict(r) for r in rows]}
    finally:
        conn.close()


# ── POST /checklist/{slope_id} ────────────────────────────────────────────────
#
# Marque une pente comme "faite".
# Si elle est déjà dans la checklist, met à jour la note et la date.
# Sinon, crée une nouvelle entrée.
#
# ON CONFLICT (slope_id) DO UPDATE : c'est un "upsert" —
# insert si absent, update si déjà présent. Évite les doublons.

@router.post("/{slope_id}")
def mark_done(slope_id: int, entry: ChecklistEntry):
    conn = get_connection()
    try:
        cur = conn.cursor()

        # Vérifier que la pente existe
        cur.execute("SELECT id, road_name FROM slopes WHERE id = %s", [slope_id])
        slope = cur.fetchone()
        if not slope:
            raise HTTPException(status_code=404, detail=f"Pente {slope_id} introuvable")

        # Upsert : insert ou update si déjà présent
        cur.execute("""
            INSERT INTO checklist (slope_id, done, done_at, note)
            VALUES (%s, TRUE, NOW(), %s)
            ON CONFLICT (slope_id)
            DO UPDATE SET done = TRUE, done_at = NOW(), note = EXCLUDED.note
            RETURNING id, done_at
        """, [slope_id, entry.note])

        result = cur.fetchone()
        conn.commit()

        return {
            "message": f"Pente '{slope['road_name']}' marquée comme faite.",
            "checklist_id": result["id"],
            "done_at": str(result["done_at"])
        }
    finally:
        conn.close()


# ── DELETE /checklist/{slope_id} ──────────────────────────────────────────────
#
# Décoche une pente (supprime l'entrée de la checklist).

@router.delete("/{slope_id}")
def unmark_done(slope_id: int):
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM checklist WHERE slope_id = %s RETURNING id",
            [slope_id]
        )
        deleted = cur.fetchone()
        conn.commit()

        if not deleted:
            raise HTTPException(status_code=404, detail="Pente non trouvée dans la checklist")

        return {"message": "Pente décochée."}
    finally:
        conn.close()
