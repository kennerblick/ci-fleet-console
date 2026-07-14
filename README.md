# CI Fleet Console

**A self-hosted web console to manage GitLab CI/CD pipelines across dozens or
hundreds of projects at once** — built for homelabs and ops teams that use one
GitLab group with many sub-projects (servers, routers, appliances) and got
tired of clicking through them one by one.

Keywords: GitLab CI dashboard · multi-project pipeline monitor · fleet
management · infrastructure automation · `.gitlab-ci.yml` editor · DevOps ·
FastAPI · self-hosted.

## Features

- **Project tree** of an entire GitLab group (incl. subgroups) with live
  pipeline status dots and a mini "sparkline" of the last 5 runs per project
- **Pipelines & jobs**: stage view including **trigger jobs (bridges)** and
  their **child/downstream pipelines**, with play / retry / cancel per job
- **Group job matrix**: one table showing every job that all projects of a
  subgroup have in common — the status of e.g. `backup` across your whole
  router fleet at a glance
- **`.gitlab-ci.yml` editor** with commit, full version history, restore, and
  one-click insertion of **standard templates** from a templates repository
- **CI-VARS**: declare required variables in a comment block inside the CI
  file; the console verifies them (project + inherited group variables),
  offers input fields for missing ones and **blocks commits/pipeline starts**
  until required variables exist
- **Pipeline start** with custom ref and variables
- **User management**: local users (scrypt) and optional **Active Directory /
  LDAP** login with group-based roles, connection test button, per-user GitLab
  tokens with a shared default fallback
- **Fast**: file-based cache with stale-while-revalidate, parallel GitLab
  requests, gzip, lazy loading — the UI stays responsive even with large groups

## Quick start (Docker)

```bash
docker compose up -d --build
```

- First start creates a local `admin` user. Set `ADMIN_PASSWORD` in
  `docker-compose.yml` for the first run (remove afterwards) or find the
  generated password in `docker compose logs`.
- All state lives in the `./data` volume (`chown -R 10001:10001 data` once).
- TLS: issue a certificate from your internal CA (SAN = FQDN), place
  `console.pem` / `console.key` and your root CA into `./certs` — see the
  comments in `docker-compose.yml`. `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`
  make the console verify your GitLab and LDAPS server against that CA.
- Log in, open **⚙ Konfiguration**, enter your GitLab URL, a personal access
  token (scope `api`) and the root group path — done.

## Development

```bash
pip install -r requirements-dev.txt
python -m pytest
uvicorn app.main:app --reload --port 8090
```

Layered layout: `app/routers` (thin HTTP endpoints, Pydantic-validated) →
`app/services` (GitLab domain logic) → infrastructure (`settings_store`,
`gitlab_client`, `cache`, `security`, `ad`). See `README` sections in the code
for details. UI is a dependency-free single-page app (vanilla JS, no build
step). Note: code comments and the UI language are German.

## Security notes

scrypt password hashing, server-side sessions (HttpOnly/SameSite cookie with
bearer-token fallback), login lockout after repeated failures, server-side
role checks (admin/user), enforced LDAPS certificate validation, LDAP filter
escaping, per-user token isolation for cache and clients, non-root container,
config files written with mode 0600. GitLab tokens are stored server-side in
`./data` — protect the host and backups accordingly. No 2FA/audit log; put an
SSO proxy (e.g. Authentik/Keycloak) in front if you need more.

## License

MIT
