"""Anonymisation RGPD des feedbacks — à lancer manuellement ou via cron.

Deux règles issues du mémo RGPD (docs/RGPD-memo.md) :
  - J+30  : purge du champ ``commentaire`` (risque de ré-identification par le texte libre)
  - J+180 : remplacement de ``stagiaire_email`` par un hash SHA-256 tronqué à 12 chars

Lancement :
    uv run python -m scripts.anonymize_feedbacks

Idempotent : une 2e exécution ne touche que les lignes non encore anonymisées.
"""

from __future__ import annotations

import hashlib
from datetime import date, timedelta

from sqlalchemy import text

from collect._common import db_session, log

SEUIL_COMMENTAIRE = 30    # jours
SEUIL_EMAIL = 180         # jours


def _hash_email(email: str) -> str:
    return hashlib.sha256(email.encode()).hexdigest()[:12]


def purge_commentaires(session, today: date) -> int:
    """Efface les commentaires de plus de SEUIL_COMMENTAIRE jours."""
    cutoff = today - timedelta(days=SEUIL_COMMENTAIRE)
    result = session.execute(
        text(
            """
            UPDATE feedbacks
            SET commentaire = NULL
            WHERE date_saisie < :cutoff
              AND commentaire IS NOT NULL
            """
        ),
        {"cutoff": cutoff},
    )
    return result.rowcount


def anonymize_emails(session, today: date) -> int:
    """Remplace stagiaire_email par son hash SHA-256 (12 chars) après SEUIL_EMAIL jours.

    Les lignes déjà anonymisées (email de 12 chars, pas de '@') sont ignorées.
    """
    cutoff = today - timedelta(days=SEUIL_EMAIL)
    rows = session.execute(
        text(
            """
            SELECT id, stagiaire_email
            FROM feedbacks
            WHERE date_saisie < :cutoff
              AND stagiaire_email IS NOT NULL
              AND stagiaire_email LIKE '%@%'
            """
        ),
        {"cutoff": cutoff},
    ).fetchall()

    for row in rows:
        session.execute(
            text("UPDATE feedbacks SET stagiaire_email = :h WHERE id = :id"),
            {"h": _hash_email(row.stagiaire_email), "id": row.id},
        )
    return len(rows)


def run() -> None:
    today = date.today()
    log.info("anonymize_feedbacks.start", today=today.isoformat())
    with db_session() as session:
        nb_commentaires = purge_commentaires(session, today)
        nb_emails = anonymize_emails(session, today)
    log.info(
        "anonymize_feedbacks.done",
        commentaires_purges=nb_commentaires,
        emails_anonymises=nb_emails,
    )


if __name__ == "__main__":
    run()
