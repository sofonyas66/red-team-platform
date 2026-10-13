"""
db/ingestion_ops.py — Postgres-backed ingestion log operations.

Replaces the JSON file tracker (INGESTION_TRACKER_FILE) from the original api/main.py.
All functions are synchronous (SQLAlchemy sync engine) to keep the call sites simple —
the API routes call these in a thread-safe manner since they already hold the GIL.
"""
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from config import DATABASE_URL
from db.models import IngestionRecord, IngestionStatus

# Convert async URL to sync for SQLAlchemy sync operations
_sync_url = DATABASE_URL.replace("+asyncpg", "+psycopg2").replace("postgresql+asyncpg", "postgresql+psycopg2")
_engine = create_engine(_sync_url, pool_pre_ping=True)


def is_already_ingested(org_id: str, file_hash: str) -> bool:
    """
    Return True if this org has already ingested a file with this hash.
    Per-org dedup: the same file CAN be ingested by different orgs independently
    (the unique constraint is on (org_id, file_hash), not just file_hash).
    """
    with Session(_engine) as session:
        stmt = select(IngestionRecord).where(
            IngestionRecord.org_id == uuid.UUID(org_id),
            IngestionRecord.file_hash == file_hash,
            IngestionRecord.status == IngestionStatus.complete,
        )
        return session.scalar(stmt) is not None


def record_ingestion(
    org_id: str,
    engagement_id: str,
    file_hash: str,
    filename: str,
    node_count: int,
    edge_count: int,
    ingested_by: str,
) -> IngestionRecord:
    """
    Insert a completed ingestion record.
    Raises IntegrityError if the unique constraint (org_id, file_hash) fires
    (second-path backstop — is_already_ingested should catch it first).
    """
    with Session(_engine) as session:
        record = IngestionRecord(
            org_id=uuid.UUID(org_id),
            engagement_id=uuid.UUID(engagement_id),
            file_hash=file_hash,
            filename=filename,
            node_count=node_count,
            edge_count=edge_count,
            status=IngestionStatus.complete,
            ingested_at=datetime.utcnow(),
            ingested_by=uuid.UUID(ingested_by),
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def get_ingestion_record_by_hash(org_id: str, file_hash: str) -> Optional[IngestionRecord]:
    """Return the IngestionRecord for this org + hash, or None."""
    with Session(_engine) as session:
        stmt = select(IngestionRecord).where(
            IngestionRecord.org_id == uuid.UUID(org_id),
            IngestionRecord.file_hash == file_hash,
        )
        return session.scalar(stmt)
