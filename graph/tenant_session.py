"""
graph/tenant_session.py — Tenant-scoped async Neo4j session wrapper.

ALL Cypher execution for engagement / AD data MUST go through TenantSession.
Direct driver.session() calls are only permitted in:
  graph/connection.py, graph/tenant_session.py, graph/schema.py
  (schema bootstrap — not per-tenant).
"""
import logging
from graph.connection import driver

logger = logging.getLogger(__name__)

STRICT_MODE = False  # set True once all call sites are migrated; raises instead of warns


class TenantSessionError(Exception):
    pass


class TenantSession:
    """
    Async context manager for tenant-scoped Neo4j access.

    All Cypher execution in this codebase for AD / engagement data MUST go
    through this class.  Constructed with org_id (required) and optionally
    engagement_id.  Refuses to run without org_id.  Warns (or raises in
    STRICT_MODE) if a query string doesn't reference $org_id.

    Usage::

        async with TenantSession(org_id=user.org_id, engagement_id=eid) as ts:
            result = await ts.run("MATCH (n {org_id: $org_id}) RETURN n")
    """

    def __init__(self, org_id: str, engagement_id: str | None = None):
        if not org_id:
            raise TenantSessionError(
                "TenantSession requires org_id — refusing unscoped graph access"
            )
        self.org_id = org_id
        self.engagement_id = engagement_id
        self._session = None

    # ── Sync check helper (no I/O — stays sync intentionally) ─────────────
    def _check_query_scoped(self, query: str):
        if "$org_id" not in query and "org_id" not in query:
            msg = f"Query does not reference org_id — likely unscoped: {query[:120]}"
            if STRICT_MODE:
                raise TenantSessionError(msg)
            logger.warning(msg)

    # ── Async context manager ──────────────────────────────────────────────
    async def __aenter__(self):
        self._session = driver.session()
        return self

    async def __aexit__(self, *exc):
        await self._session.close()

    async def run(self, query: str, **params):
        self._check_query_scoped(query)
        params.setdefault("org_id", self.org_id)
        if self.engagement_id:
            params.setdefault("engagement_id", self.engagement_id)
        return await self._session.run(query, **params)
