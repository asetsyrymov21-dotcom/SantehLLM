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
