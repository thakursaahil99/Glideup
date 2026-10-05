# Deploying GlideUp (Oracle Cloud Always Free)

One VM runs the whole stack with Docker Compose. Caddy serves HTTPS with a free Let's Encrypt
certificate. Cost: **$0** on Oracle's Always Free ARM VM (up to 4 OCPU / 24 GB RAM).

## 1. Accounts and keys (about 20 minutes, one time)

1. **Oracle Cloud**: sign up at cloud.oracle.com. A card is needed for identity checks; Always Free
   resources are never charged.
2. **GitHub Models token**: github.com → Settings → Developer settings → Fine-grained tokens →
   new token with the **Models: read** permission.
3. **Google OAuth client**: console.cloud.google.com → APIs & Services → Credentials → OAuth
   client ID (Web). Set the redirect URI after you know your domain (step 3):
   `https://<DOMAIN>/api/auth/callback/google`.

## 2. Create the VM

Compute → Instances → Create:
- Image: **Ubuntu 24.04**. Shape: **VM.Standard.A1.Flex**, 4 OCPU and 24 GB RAM (Always Free).
- Add your SSH public key. Boot volume: 100 GB is fine (200 GB total is free).
- Networking → the subnet's **Security List** → add ingress rules for TCP **80** and **443**
  from `0.0.0.0/0`.

If you see "Out of capacity" for A1, try another availability domain or retry later. That is
common on the free tier.

## 3. Install and start

```bash
ssh ubuntu@<VM_IP>
git clone <your repo URL> glideup && cd glideup
./deploy/setup-vm.sh          # installs Docker; log out/in once, then run it again
nano .env                     # fill GITHUB_MODELS_TOKEN, Google OAuth, ADMIN_EMAILS, ACME_EMAIL
./deploy/deploy.sh            # builds, starts, waits until https://<DOMAIN> answers
```

`setup-vm.sh` generates every secret and sets `DOMAIN` to `<ip-with-dashes>.sslip.io`. That is
a free hostname that resolves to your IP, so HTTPS works without buying a domain. To use your
own domain, point an A record at the VM IP and change `DOMAIN` in `.env`.

The first start pulls the Ollama models (about 3 GB) used for embeddings and as the AI fallback.
Matching and recommendations need the embedding model, so give it a few minutes.

## 4. Updating

```bash
cd glideup && git pull && ./deploy/deploy.sh
```

Migrations run automatically (the `migrate` service) before the API starts.

## 5. Operations

| Task | Command |
|---|---|
| Logs | `docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f api worker web` |
| Status | `docker compose -f docker-compose.yml -f docker-compose.prod.yml ps` |
| Grafana | `ssh -L 3001:localhost:3001 ubuntu@<VM_IP>`, then open http://localhost:3001 |
| DB backup | `docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T postgres pg_dump -U glideup glideup \| gzip > backup-$(date +%F).sql.gz` |
| Make someone admin | add their email to `ADMIN_EMAILS` and redeploy, or use Admin → Users |

## Known limits

- **Code sandbox on ARM:** the official Piston image may not exist for ARM. `deploy.sh` then
  starts everything else and logs a warning. Coding tests show "sandbox unavailable", and
  System Health shows the sandbox as down. Framework tests, interviews and everything else
  keep working.
- **Free LLM quotas:** GitHub Models' free tier has per-day request limits. Set a per-user daily
  token budget in Admin → AI / LLM settings. When the quota runs out, calls fall back to Ollama
  on the VM, which is slower but keeps working.
