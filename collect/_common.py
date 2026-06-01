"""Outillage commun à tous les collecteurs Nodalys.

Convention : un collecteur expose une fonction ``run()`` qui :
1. récupère les enregistrements bruts (API, CSV…)
2. valide / normalise avec pydantic
3. upsert dans Postgres
4. logge un résumé (nb lus, nb insérés, nb mis à jour, nb ignorés)

Toutes les fonctions ci-dessous sont réutilisables — voir
``collect/sessions.py`` pour un exemple complet d'utilisation.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from typing import Iterator

import httpx
import structlog
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from tenacity import retry, stop_after_attempt, wait_exponential

load_dotenv()

structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ]
)

log = structlog.get_logger()


def get_db_url() -> str:
    url = os.environ.get("DB_URL")
    if not url:
        raise RuntimeError(
            "DB_URL n'est pas définie. Copie .env.example en .env et renseigne-la."
        )
    return url


def get_api_base_url() -> str:
    return os.environ.get("NODALYS_API_BASE_URL", "http://localhost:8001")


def make_engine() -> Engine:
    return create_engine(get_db_url(), future=True)


@contextmanager
def db_session() -> Iterator[Session]:
    engine = make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


@retry(stop=stop_after_attempt(5), wait=wait_exponential(min=1, max=30))
def http_get_json(url: str, **kwargs) -> dict:
    """GET + retry exponentiel — convention partagée par tous les collecteurs API."""
    with httpx.Client(timeout=10.0) as client:
        response = client.get(url, **kwargs)
        if response.status_code == 429:
            # Respect Retry-After header if present, otherwise wait 10s
            wait = int(response.headers.get("Retry-After", 10))
            time.sleep(wait)
        response.raise_for_status()
        return response.json()
