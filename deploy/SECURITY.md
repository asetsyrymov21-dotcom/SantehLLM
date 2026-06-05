# VPS Security Baseline

Reusable minimum security checklist for VPS projects. Apply this before exposing
any new bot, API, admin panel, database, or worker to the internet.

## Core Rule

Expose only what must be public.

Default for Docker projects:

- web app/API: not published unless needed
- bot/worker: no published ports
- database/cache/queue: no published ports
- admin tools: localhost-only or VPN-only

If a service is only used by other containers, use Docker service names and
internal networking instead of host ports.

Example:

```yaml
services:
  api:
    expose:
      - "8000"

  bot:
    environment:
      API_BASE_URL: http://api:8000/api/v1
```

If host access is required, bind to localhost with a unique project port:

```yaml
services:
  api:
    ports:
      - "127.0.0.1:18080:8000"
```

Do not bind private APIs, databases, queues, dashboards, or debug servers to
`0.0.0.0`.

## Firewall

Use deny-by-default inbound rules.

Typical public VPS baseline:

```bash
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status verbose
```

Adjust SSH port if it is not `22`.

Do not open application ports such as `3000`, `5000`, `8000`, `8080`, `5432`,
`6379`, `27017`, `9000`, or `15672` unless there is a deliberate public need and
proper protection.

## SSH

Use key-based SSH and disable risky login modes.

Recommended `/etc/ssh/sshd_config` values:

```text
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes
```

Validate and restart:

```bash
sshd -t
systemctl restart ssh
```

Keep the current SSH session open while testing a second login, so you do not
lock yourself out.

## Brute-Force Protection

Install fail2ban or an equivalent tool:

```bash
apt update
apt install -y fail2ban
systemctl enable --now fail2ban
fail2ban-client status sshd
```

## Docker Hardening

Prefer these defaults:

```yaml
services:
  app:
    restart: unless-stopped
    security_opt:
      - no-new-privileges:true
```

In Dockerfiles, run app code as a non-root user:

```dockerfile
RUN addgroup --system app && adduser --system --ingroup app app
USER app
```

Avoid:

- `privileged: true`
- `network_mode: host`
- mounting `/var/run/docker.sock`
- mounting broad host paths like `/`, `/root`, or `/home`
- running production containers as root when not required

## Databases And Internal Services

Databases, caches, queues, and object stores should normally be internal only.

Examples of ports that should not be public by default:

- PostgreSQL: `5432`
- Redis: `6379`
- MongoDB: `27017`
- RabbitMQ: `5672`, `15672`
- MinIO: `9000`, `9001`
- Elasticsearch/OpenSearch: `9200`

Use Docker internal networking, VPN, SSH tunnel, or localhost bind if maintenance
access is needed.

## Reverse Proxy And TLS

Public HTTP services should be behind nginx, Caddy, Traefik, or a similar reverse
proxy with HTTPS.

Recommended shape:

```text
internet -> 80/443 reverse proxy -> localhost/internal app port
```

Do not expose multiple raw app ports publicly when one reverse proxy can route
domains safely.

## Application Security Defaults

For APIs and admin panels:

- require authentication before exposing to the internet
- disable debug mode in production
- configure CORS narrowly
- add request size limits for uploads
- validate uploaded file types
- avoid returning stack traces to users
- log security-relevant failures without logging secrets

For bots:

- run only one polling instance per token
- never reuse production bot tokens in local long-running containers
- prefer separate dev/prod tokens when testing

## Secrets

Never commit real secrets.

Common secrets to keep only in `.env`, VPS secret storage, or GitHub Actions
secrets:

- bot tokens
- API keys
- database passwords
- JWT/session secrets
- SSH private keys
- webhook signing secrets

Rotate secrets if they were committed, pasted into logs, or shown in command
output.

Avoid sharing command output from:

```bash
docker compose config
env
printenv
cat .env
```

These can expand and reveal secrets.

## Deployment Checks

Before and after deploy:

```bash
docker compose ps
ss -tulpn
ufw status verbose
```

Expected:

- only intentional public ports are listening
- no public database/cache/queue ports
- bot/worker containers publish no ports
- app containers do not require root unless justified
- production `.env` exists only on the server

## Backups

For stateful services, create a backup before migrations and service restarts.

PostgreSQL baseline:

```bash
docker compose up -d db
docker compose exec -T db sh -c \
  'pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-app}" --format=custom' \
  > backups/postgres/app-postgres-$(date -u +%Y%m%dT%H%M%SZ).dump
```

Keep restore instructions next to the deploy instructions, test them after the
first production import, and copy critical backups off the VPS when the data
becomes business-critical.

## Project Checklist

For every new project, decide explicitly:

- Which service is public?
- Which ports are published to the host?
- Which services are internal-only?
- Is HTTPS configured?
- Is authentication required?
- Are secrets out of Git?
- Is SSH hardened?
- Is firewall deny-by-default?
- Are containers non-root where practical?
- Is there a backup/restore plan for production data?
