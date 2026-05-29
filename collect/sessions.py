"""Collecteur — sessions de formation Nodalys.

C'EST LE PATTERN DE RÉFÉRENCE de ce repo. Tout autre collecteur doit s'en
inspirer (nommage, structure, logging, upsert idempotent).

Source : API Nodalys, ``GET /api/sessions`` (mockée pour le développement).
Cible  : tables ``clients`` et ``sessions`` (Postgres).

Lancement :
    uv run python -m collect.sessions
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy import text

from collect._common import (
    db_session,
    get_api_base_url,
    http_get_json,
    log,
)


class StagiairePayload(BaseModel):
    """Schéma d'un stagiaire — allow-list explicite, telephone_personnel exclu (RGPD)."""

    model_config = {"extra": "ignore"}

    id: int
    session_id: int
    prenom: str
    nom: str
    email: str


class SessionPayload(BaseModel):
    """Schéma d'une session telle que la renvoie l'API Nodalys."""

    id: int
    code: str = Field(min_length=3, max_length=64)
    titre: str
    client_id: int
    client_raison_sociale: str
    date_debut: date
    date_fin: date
    duree_heures: int = Field(ge=1)
    places_max: int = Field(ge=1)


def fetch_sessions() -> list[SessionPayload]:
    """Appelle l'API mock et valide la charge utile via pydantic."""
    base = get_api_base_url()
    payload = http_get_json(f"{base}/api/sessions")
    items = [SessionPayload.model_validate(item) for item in payload["items"]]
    log.info("collect.sessions.fetched", count=len(items))
    return items


def upsert_clients(session, sessions_payload: list[SessionPayload]) -> int:
    """Upsert idempotent des clients référencés par les sessions."""
    seen: dict[int, str] = {}
    for s in sessions_payload:
        seen[s.client_id] = s.client_raison_sociale
    inserted = 0
    for client_id, raison in seen.items():
        result = session.execute(
            text(
                """
                INSERT INTO clients (id, siret, raison_sociale)
                VALUES (:id, :siret, :raison)
                ON CONFLICT (id) DO UPDATE
                  SET raison_sociale = EXCLUDED.raison_sociale
                """
            ),
            {"id": client_id, "siret": f"FR{client_id:011d}", "raison": raison},
        )
        inserted += result.rowcount or 0
    return inserted


def upsert_sessions(session, sessions_payload: list[SessionPayload]) -> int:
    """Upsert idempotent — clé naturelle : ``id``."""
    inserted = 0
    for s in sessions_payload:
        result = session.execute(
            text(
                """
                INSERT INTO sessions (
                    id, code, titre, client_id, date_debut, date_fin,
                    duree_heures, places_max
                )
                VALUES (
                    :id, :code, :titre, :client_id, :date_debut, :date_fin,
                    :duree_heures, :places_max
                )
                ON CONFLICT (id) DO UPDATE
                  SET code = EXCLUDED.code,
                      titre = EXCLUDED.titre,
                      client_id = EXCLUDED.client_id,
                      date_debut = EXCLUDED.date_debut,
                      date_fin = EXCLUDED.date_fin,
                      duree_heures = EXCLUDED.duree_heures,
                      places_max = EXCLUDED.places_max
                """
            ),
            s.model_dump(exclude={"client_raison_sociale"}),
        )
        inserted += result.rowcount or 0
    return inserted


def upsert_stagiaires(session, sessions_payload: list[SessionPayload]) -> int:
    """Collecte des stagiaires (pagination cursor) et upsert idempotent.

    L'email n'est stocké que si la session du stagiaire est encore active
    (date_fin >= aujourd'hui) — exigence RGPD (sur-collecte).
    """
    base = get_api_base_url()
    active_session_ids = {
        s.id for s in sessions_payload if s.date_fin >= date.today()
    }

    cursor: str | None = None
    inserted = 0
    while True:
        params = {"cursor": cursor} if cursor else {}
        payload = http_get_json(f"{base}/api/stagiaires", params=params)
        for item in payload["items"]:
            stagiaire = StagiairePayload.model_validate(item)
            email = stagiaire.email if stagiaire.session_id in active_session_ids else None
            result = session.execute(
                text(
                    """
                    INSERT INTO stagiaires (id, session_id, prenom, nom, email)
                    VALUES (:id, :session_id, :prenom, :nom, :email)
                    ON CONFLICT (id) DO UPDATE
                      SET session_id = EXCLUDED.session_id,
                          prenom = EXCLUDED.prenom,
                          nom = EXCLUDED.nom,
                          email = EXCLUDED.email
                    """
                ),
                {
                    "id": stagiaire.id,
                    "session_id": stagiaire.session_id,
                    "prenom": stagiaire.prenom,
                    "nom": stagiaire.nom,
                    "email": email,
                },
            )
            inserted += result.rowcount or 0
        cursor = payload.get("next_cursor")
        if not cursor:
            break

    log.info("collect.stagiaires.upserted", count=inserted)
    return inserted


def run() -> None:
    log.info("collect.sessions.start")
    sessions_payload = fetch_sessions()
    with db_session() as session:
        nb_clients = upsert_clients(session, sessions_payload)
        nb_sessions = upsert_sessions(session, sessions_payload)
        nb_stagiaires = upsert_stagiaires(session, sessions_payload)
    log.info(
        "collect.sessions.done",
        clients=nb_clients,
        sessions=nb_sessions,
        stagiaires=nb_stagiaires,
    )


if __name__ == "__main__":
    run()
