#!/usr/bin/env sh
# Деплой на VPS: обновить код и пересобрать контейнеры. Запуск из корня репозитория: ./scripts/deploy.sh
set -eu
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Нет .env: скопируй сюда .env.prod (см. docs/DEPLOY.md)"; exit 1; }

git pull --ff-only

# Дополнительные сервисы: Caddy (HTTPS для Mini App), если задан домен; xray (прокси для Telegram), если есть конфиг
PROFILES=""
grep -q '^WEBAPP_DOMAIN=.' .env && PROFILES="$PROFILES --profile https"
[ -f xray/config.json ] && PROFILES="$PROFILES --profile proxy"

# shellcheck disable=SC2086
docker compose $PROFILES up -d --build
docker compose $PROFILES ps
docker compose logs --tail=20 bot
