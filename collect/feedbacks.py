"""Collecteur — feedbacks de fin de session (CSV).

Source : fichiers CSV dans ``data/feedbacks/*.csv``.
Cible  : table ``feedbacks``.

Lancement :
    uv run python -m collect.feedbacks
"""

from __future__ import annotations

import csv
from datetime import date
from pathlib import Path

from pydantic import BaseModel, Field, field_validator, ValidationError
from sqlalchemy import text

from collect._common import db_session, log

DATA_DIR = Path(__file__).parent.parent / "data" / "feedbacks"


class FeedbackRow(BaseModel):
    """Schéma d'une ligne CSV feedback après validation."""

    session_id: int
    stagiaire_email: str | None = None
    date_saisie: date
    note_globale: int = Field(ge=1, le=5)
    commentaire: str | None = None

    @field_validator("stagiaire_email", "commentaire", mode="before")
    @classmethod
    def empty_str_to_none(cls, v: str) -> str | None:
        return v.strip() or None


def fetch_feedbacks(csv_path: Path) -> list[FeedbackRow]:
    """Lit un fichier CSV de feedbacks et valide chaque ligne via pydantic."""
    rows: list[FeedbackRow] = []
    with csv_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=";")
        for lineno, raw in enumerate(reader, start=2):
            try:
                rows.append(FeedbackRow.model_validate(raw))
            except ValidationError as exc:
                log.warning(
                    "collect.feedbacks.row_invalid",
                    file=csv_path.name,
                    line=lineno,
                    error=str(exc),
                )
    log.info("collect.feedbacks.file_read", file=csv_path.name, count=len(rows))
    return rows


def upsert_feedbacks(session, rows: list[FeedbackRow], source_csv: str) -> int:
    """Upsert idempotent — clé naturelle : (session_id, stagiaire_email, date_saisie)."""
    inserted = 0
    for row in rows:
        result = session.execute(
            text(
                """
                INSERT INTO feedbacks (
                    session_id, stagiaire_email, date_saisie,
                    note_globale, commentaire, source_csv
                )
                VALUES (
                    :session_id, :stagiaire_email, :date_saisie,
                    :note_globale, :commentaire, :source_csv
                )
                ON CONFLICT ON CONSTRAINT uq_feedbacks_session_email_date DO UPDATE
                  SET note_globale = EXCLUDED.note_globale,
                      commentaire  = EXCLUDED.commentaire,
                      source_csv   = EXCLUDED.source_csv
                """
            ),
            {**row.model_dump(), "source_csv": source_csv},
        )
        inserted += result.rowcount or 0
    return inserted


def run() -> None:
    log.info("collect.feedbacks.start")
    csv_files = sorted(DATA_DIR.glob("*.csv"))
    total = 0
    with db_session() as session:
        for csv_path in csv_files:
            rows = fetch_feedbacks(csv_path)
            nb = upsert_feedbacks(session, rows, csv_path.name)
            total += nb
    log.info("collect.feedbacks.done", inserted=total)


if __name__ == "__main__":
    run()
