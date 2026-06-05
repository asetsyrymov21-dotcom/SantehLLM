# Deploy

This project deploys from GitHub to a VPS with GitHub Actions.

## Local push

From the project root:

```powershell
.\scripts\git_push.ps1 -Message "update importer pipeline" -RemoteUrl "https://github.com/USER/REPO.git"
```

After the remote is configured once:

```powershell
.\scripts\git_push.ps1 -Message "update importer pipeline"
```

Use `-SkipTests` only for documentation-only changes.

## VPS setup

Install Docker and Docker Compose on the VPS, then clone the repository:

```bash
sudo mkdir -p /opt/santeh
sudo chown "$USER:$USER" /opt/santeh
git clone https://github.com/USER/REPO.git /opt/santeh
cd /opt/santeh
cp .env.example .env
```

Edit `.env` on the VPS and add production secrets.

For large Telegram uploads, the VPS compose runs a local Telegram Bot API
container. Add these values from https://my.telegram.org/apps to `.env`:

```bash
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=your_api_hash
```

The bot itself still uses `TELEGRAM_BOT_TOKEN`. Managers can keep uploading
Excel files in Telegram; the local Bot API removes the small public Bot API
download limit.

Run the first deploy manually:

```bash
APP_DIR=/opt/santeh bash deploy/deploy_on_vps.sh
```

## GitHub secrets

Add these repository secrets in GitHub:

- `VPS_HOST`: VPS IP or domain.
- `VPS_USER`: SSH user.
- `VPS_SSH_KEY`: private SSH key allowed to connect to the VPS.
- `VPS_SSH_PORT`: SSH port, usually `22`.
- `VPS_APP_DIR`: app path on VPS, for example `/opt/santeh`.

On every push to `main`, GitHub Actions will SSH into the VPS, pull the latest code,
run migrations, rebuild containers, and restart the API and bot.

## PostgreSQL backups

The VPS deploy script creates a PostgreSQL backup before running migrations or
restarting the app:

```text
/opt/santeh/backups/postgres/santeh-postgres-YYYYMMDDTHHMMSSZ.dump
```

The backup uses PostgreSQL custom format, so restore it with `pg_restore`.
Defaults can be changed when running the deploy:

```bash
BACKUP_DIR=/opt/santeh/backups/postgres BACKUP_KEEP_DAYS=14 APP_DIR=/opt/santeh bash deploy/deploy_on_vps.sh
```

Restore example on the VPS:

```bash
cd /opt/santeh
docker compose -f docker-compose.vps.yml up -d db
docker compose -f docker-compose.vps.yml exec -T db sh -c \
  'dropdb -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-santeh}" --if-exists && createdb -U "${POSTGRES_USER:-postgres}" "${POSTGRES_DB:-santeh}"'
docker compose -f docker-compose.vps.yml exec -T db sh -c \
  'pg_restore -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-santeh}" --clean --if-exists' \
  < backups/postgres/santeh-postgres-YYYYMMDDTHHMMSSZ.dump
```
