TASK 0 (Verifier): baseline audit of the current tree. Read-only.
1. Standard checks: the import check, pyflakes on backend/api/main.py, and pnpm build in frontend (last known failure: app/page.tsx:366).
2. List the registered FastAPI routes (path and methods).
3. grep in frontend (exclude node_modules and .next) for: Acme|Nightfall|svc-backup|84.6|68 / 100|helpdesk.
4. Is there a GET /me route? Show it. Does GET /graph/stats filter by org_id? Quote the lines.
5. The topbar engagement selector: where is it, what does it store, which request sends the engagement_id, and does the backend check ownership of it?
6. The Attack paths table: which file and endpoint, what source and target does it send, and what is the "GNN fallback scoring"? Quote the code and the formula.
7. With the API running: POST /ingest/bloodhound with no token should return 401, and with a valid token plus engagement_id=test it should return 422. Use a dummy file created in /tmp.
8. Read-only: what are the root-level public/ and postman/ folders, and does anything reference them?
