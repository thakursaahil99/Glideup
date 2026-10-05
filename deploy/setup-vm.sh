#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04/24.04 VM (Oracle Cloud Always Free ARM works well).
# Usage (on the VM, inside the cloned repo):  ./deploy/setup-vm.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v docker >/dev/null; then
  echo "==> Installing Docker"
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER"
  echo "Docker installed. Log out and back in (or run: newgrp docker), then re-run this script."
  exit 0
fi

echo "==> Opening ports 80/443 in the VM firewall (Oracle images block them by default)"
if command -v iptables >/dev/null; then
  for port in 80 443; do
    sudo iptables -C INPUT -p tcp --dport "$port" -j ACCEPT 2>/dev/null \
      || sudo iptables -I INPUT 6 -p tcp -m state --state NEW --dport "$port" -j ACCEPT
  done
  sudo iptables -C INPUT -p udp --dport 443 -j ACCEPT 2>/dev/null \
    || sudo iptables -I INPUT 6 -p udp --dport 443 -j ACCEPT
  if command -v netfilter-persistent >/dev/null; then sudo netfilter-persistent save; fi
fi

echo "==> Swap (helps model loading and builds on small VMs)"
if ! swapon --show | grep -q /swapfile; then
  sudo fallocate -l 4G /swapfile && sudo chmod 600 /swapfile
  sudo mkswap /swapfile && sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

if [ ! -f .env ]; then
  echo "==> Creating .env with generated secrets"
  cp .env.production.example .env
  while grep -q '=generated$' .env; do
    key=$(grep -m1 '=generated$' .env | cut -d= -f1)
    sed -i "s|^${key}=generated$|${key}=$(openssl rand -hex 32)|" .env
  done
  ip=$(curl -fsS https://api.ipify.org || true)
  if [ -n "$ip" ]; then
    sed -i "s|^DOMAIN=$|DOMAIN=${ip//./-}.sslip.io|" .env
  fi
  chmod 600 .env
  echo "Now edit .env: GITHUB_MODELS_TOKEN, Google OAuth (AUTH_GOOGLE_ID/SECRET, GOOGLE_CLIENT_ID),"
  echo "ADMIN_EMAILS and ACME_EMAIL. Then run ./deploy/deploy.sh"
else
  echo ".env already exists; leaving it alone."
fi
