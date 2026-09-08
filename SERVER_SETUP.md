# Server setup reference

`server_setup.sh` supports Ubuntu and uses `set -euo pipefail`. It must run from the repository root with sudo.

## Before running

- Point the intended DNS A/AAAA record at the VPS.
- Confirm ports 22, 80, and 443 are allowed by the VPS provider firewall.
- Populate `.env`; never commit it.
- Keep SSH access open before enabling UFW.

Required production values are documented in `.env.example`. The script generates missing Django, PostgreSQL, PAL callback, and activity API secrets. It does not fabricate Google or PAL credentials.

## TLS

When both `DOMAIN` and `SSL_EMAIL` are present, the script temporarily stops Nginx, runs Certbot standalone, writes the TLS Nginx configuration from `nginx/app-ssl.conf.template`, and restarts the stack. Certbot renewal can be tested with `sudo certbot renew --dry-run`; after certificate renewal, run `docker compose restart nginx`.

## Verification

```bash
docker compose ps
curl -fsS https://DOMAIN/health/
docker compose exec web python manage.py check --deploy
```

The health response reports only Django, PostgreSQL, and Redis readiness. It exposes no hostnames or secrets.
