# CLAUDE.md – CI Fleet Console

Self-hosted web console for managing GitLab CI/CD across all sub-projects of
one GitLab group. Backend: FastAPI (Python 3.12). Frontend: dependency-free
vanilla JS single-page app (no build step). Deployment: Docker.

## Commands

- Tests:        `python -m pytest` (must stay green before every commit)
- Dev server:   `uvicorn app.main:app --reload --port 8090`
- Deploy (prod, on the docker host):
  `git pull && docker compose up -d --build`
  (never just `build` – the container is only replaced by `up`)

## Architecture (layered – keep it that way)

- `app/routers/`   thin HTTP endpoints, Pydantic-validated (schemas.py),
                   delegate to services; admin-only routers use
                   `Depends(admin_required)` from deps.py
- `app/services/`  GitLab domain logic (tree, pipelines incl. trigger
                   bridges/child pipelines, ci_file, variables/CI-VARS,
                   templates, group_matrix) – no HTTP details here
- Infrastructure:  settings_store (default + per-user config resolved via
                   ContextVar; workers need `gitlab_client.ctx_submit`),
                   gitlab_client (one client per thread+connection),
                   cache (file cache, TTL, stale-while-revalidate,
                   namespace per user connection), security (scrypt,
                   in-memory sessions, rate limit), ad (LDAPS, cert
                   validation enforced)

## Hard rules

- HTTP 401 is reserved for "session invalid". A GitLab-rejected PAT or any
  backend error must NEVER return 401 (use 400 + clear German message) –
  the frontend treats 401 as logout (with a /api/auth/me double-check).
- Trim user-pasted tokens. Never return stored tokens to the frontend.
- Never commit: data/, certs/, settings.json, users.json, auth.json,
  config.py (see .gitignore). Never put company-specific values (domains,
  hostnames, group names) into code, comments, tests or docs – use
  example.internal / devops / alice.
- Exactly ONE uvicorn worker (sessions/rate-limit/SWR guards are in-memory).
- UI texts and code comments are German; README stays English.
- Cache keys are namespaced per user connection (settings_store.scope_key) –
  do not bypass app/cache.py helpers.

## Ops context

- Runs in Docker; state lives in the ./data volume (UID 10001).
- Local host specifics (CA path, ADMIN_PASSWORD) belong in
  docker-compose.override.yml on the host, never in the repo compose.
- TLS terminates in uvicorn (certs from ./certs); REQUESTS_CA_BUNDLE /
  SSL_CERT_FILE point to the internal root CA for GitLab + LDAPS.
