#!/usr/bin/env sh
# Деплой на VPS: обновить код и пересобрать контейнеры. Запуск из корня репозитория: ./scripts/deploy.sh
set -eu
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "Нет .env: скопируй сюда .env.prod (см. docs/DEPLOY.md)"; exit 1; }

git pull --ff-only

# С доменом поднимаем ещё и Caddy (HTTPS для Mini App)
if grep -q '^WEBAPP_DOMAIN=.' .env; then
  docker compose --profile https up -d --build
else
  docker compose up -d --build
fi

docker compose ps
docker compose logs --tail=20 bot
