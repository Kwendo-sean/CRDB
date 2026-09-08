#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
step=0
status(){ step=$((step+1)); printf '
[%s/13] %s
' "$step" "$1"; }
require_root(){ if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo "Run with sudo: sudo bash server_setup.sh" >&2; exit 1; fi; }
upsert(){ local key="$1" value="$2"; if grep -q "^${key}=" .env; then sed -i "s|^${key}=.*|${key}=${value}|" .env; else printf '%s=%s
' "$key" "$value" >> .env; fi; }
secret(){ openssl rand -hex "$1"; }
status "Checking root access and supported host"; require_root; . /etc/os-release; [[ "${ID:-}" == "ubuntu" ]] || { echo "Ubuntu is required" >&2; exit 1; }
status "Updating packages"; apt-get update; DEBIAN_FRONTEND=noninteractive apt-get upgrade -y; apt-get install -y ca-certificates curl git openssl python3 ufw certbot
status "Installing Docker Engine and Compose"; if ! command -v docker >/dev/null; then install -m 0755 -d /etc/apt/keyrings; curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; chmod a+r /etc/apt/keyrings/docker.asc; echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list; apt-get update; apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; fi; systemctl enable --now docker; docker compose version
status "Configuring firewall"; ufw allow OpenSSH; ufw allow 80/tcp; ufw allow 443/tcp; ufw --force enable
status "Preparing environment"; if [[ ! -f .env ]]; then cp .env.example .env; fi; [[ -n "$(grep '^DJANGO_SECRET_KEY=' .env | cut -d= -f2-)" ]] || upsert DJANGO_SECRET_KEY "$(secret 32)"; [[ -n "$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-)" ]] || upsert POSTGRES_PASSWORD "$(secret 20)"; DB_PASSWORD=$(grep '^POSTGRES_PASSWORD=' .env | cut -d= -f2-); DB_NAME=$(grep '^POSTGRES_DB=' .env | cut -d= -f2-); DB_USER=$(grep '^POSTGRES_USER=' .env | cut -d= -f2-); DB_PASSWORD_URLENCODED=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1],safe=""))' "$DB_PASSWORD"); upsert DATABASE_URL "postgresql://${DB_USER}:${DB_PASSWORD_URLENCODED}@postgres:5432/${DB_NAME}"; [[ -n "$(grep '^PAL_CALLBACK_SECRET=' .env | cut -d= -f2-)" ]] || upsert PAL_CALLBACK_SECRET "$(secret 32)"; [[ -n "$(grep '^ACTIVITY_API_KEY=' .env | cut -d= -f2-)" ]] || upsert ACTIVITY_API_KEY "$(secret 24)"; DOMAIN_VALUE=$(grep '^DOMAIN=' .env | cut -d= -f2-); if [[ -n "$DOMAIN_VALUE" ]]; then upsert DJANGO_SECURE_SSL_REDIRECT 1; upsert DJANGO_SECURE_HSTS_SECONDS 31536000; upsert DJANGO_ALLOWED_HOSTS "${DOMAIN_VALUE},localhost,127.0.0.1"; upsert CSRF_TRUSTED_ORIGINS "https://$DOMAIN_VALUE"; upsert APP_BASE_URL "https://$DOMAIN_VALUE"; else PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}'); upsert DJANGO_SECURE_SSL_REDIRECT 0; upsert DJANGO_SECURE_HSTS_SECONDS 0; upsert DJANGO_ALLOWED_HOSTS "${PUBLIC_IP},localhost,127.0.0.1"; upsert CSRF_TRUSTED_ORIGINS "http://${PUBLIC_IP}"; upsert APP_BASE_URL "http://${PUBLIC_IP}"; echo "No DOMAIN set; serving plain HTTP on ${PUBLIC_IP}."; fi; chmod 600 .env; mkdir -p backups
status "Validating Compose configuration"; docker compose config --quiet
status "Building application images"; docker compose build --pull
status "Starting PostgreSQL and Redis"; docker compose up -d postgres redis; for _ in $(seq 1 30); do docker compose exec -T postgres pg_isready -U "$DB_USER" -d "$DB_NAME" >/dev/null 2>&1 && docker compose exec -T redis redis-cli ping | grep -q PONG && break; sleep 2; done; docker compose exec -T postgres pg_isready -U "$DB_USER" -d "$DB_NAME"; docker compose exec -T redis redis-cli ping
status "Verifying production configuration"; docker compose run --rm --no-deps -T web python manage.py check --deploy --fail-level ERROR
status "Starting application services"; docker compose up -d web celery celery-beat; docker compose exec -T web python manage.py migrate --noinput; docker compose exec -T web python manage.py collectstatic --noinput --clear; docker compose exec -T web python manage.py setup_roles
status "Starting Nginx"; docker compose up -d nginx
status "Configuring optional TLS"; set -a; . ./.env; set +a; if [[ -n "${DOMAIN:-}" && -n "${SSL_EMAIL:-}" ]]; then docker compose stop nginx; certbot certonly --standalone --non-interactive --agree-tos --email "$SSL_EMAIL" -d "$DOMAIN"; sed "s/__DOMAIN__/${DOMAIN}/g" nginx/app-ssl.conf.template > nginx/conf.d/app.conf; docker compose run --rm --no-deps -T --entrypoint nginx nginx -t -c /etc/nginx/nginx.conf; docker compose up -d --force-recreate web nginx; else echo "DOMAIN/SSL_EMAIL not set; HTTP is active. Set both and rerun for Let's Encrypt TLS."; fi
status "Installing daily backup schedule"; chmod +x deploy.sh scripts/*.sh; cat > /etc/cron.d/crdb-learning-week-backup <<EOF
15 2 * * * root cd $(pwd) && ./scripts/backup_database.sh >> /var/log/crdb-learning-week-backup.log 2>&1
EOF
status "Running health check"; set -a; . ./.env; set +a; HEALTH_URL="${APP_BASE_URL%/}/health/"; for _ in $(seq 1 30); do if curl -fsS "$HEALTH_URL"; then echo; docker compose ps; echo "Deployment ready: ${APP_BASE_URL}"; exit 0; fi; sleep 3; done; echo "Health check failed: $HEALTH_URL" >&2; docker compose logs --tail=100 web nginx; exit 1
