# Деплой на VPS

Сервер: Ubuntu 22.04/24.04, от 1 ГБ RAM, открытые порты 80 и 443 (нужны только для Mini App).
Всё работает в Docker: `db` (PostgreSQL 16), `bot` (бот + API календаря), `caddy` (HTTPS, по желанию).

## 1. Docker

```bash
curl -fsSL https://get.docker.com | sh
```

## 2. Код и настройки

```bash
git clone https://github.com/NIZHEGORODTSY/GORKY_CODE.git && cd GORKY_CODE
```

С локального компьютера скопировать прод-настройки (в git их нет — там секреты):

```bash
scp .env.prod <user>@<ip>:~/GORKY_CODE/.env
```

В `.env.prod` уже есть токен прод-бота, ключ GigaChat и пароль базы. `DATABASE_URL` смотрит на хост `db` —
так и должно быть внутри docker compose.

## 3. Календарь (Mini App) — по желанию

Telegram открывает Mini App только по HTTPS. Свой домен не обязателен: подойдёт бесплатный
`<ip-через-дефисы>.sslip.io` — он указывает на IP сервера, и Caddy получит для него сертификат Let's Encrypt.

В `.env` на сервере:

```
WEBAPP_DOMAIN=95-163-10-20.sslip.io
```

Порты 80 и 443 должны быть открыты (`ufw allow 80,443/tcp`, если включён ufw).
Без `WEBAPP_DOMAIN` бот работает полностью, просто без кнопки «Календарь».

## 4. Запуск и обновление

```bash
./scripts/deploy.sh
```

Скрипт делает `git pull`, собирает образ и поднимает контейнеры (с Caddy, если задан домен). Миграции базы
применяются автоматически при старте бота. Для обновления после нового коммита — та же команда.

## Проверка

```bash
docker compose ps                    # все сервисы running / healthy
docker compose logs -f bot           # должно быть «Run polling for bot @gorky_audio_bot»
curl -s https://$WEBAPP_DOMAIN/health   # {"ok": true}, если включён календарь
```

В Telegram: `/start` у @gorky_audio_bot, затем кнопка «Календарь» слева от поля ввода.

## Полезное

```bash
docker compose restart bot                                        # перезапуск бота
docker compose exec db pg_dump -U gorky gorky > backup.sql         # бэкап базы
docker compose exec -T db psql -U gorky gorky < backup.sql         # восстановление
```

Один токен бота нельзя запускать в двух местах одновременно: прод-токен работает только на VPS,
локально — тестовый бот из `.env`.

Профиль бота (имя, описание, аватар, команды) уже выставлен. Если поменяли тексты в `app/bot/profile.py`
или аватар — локально: `python -m scripts.setup_bot_profile .env.prod`.
