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

Telegram открывает Mini App и подписку на календарь только по HTTPS, поэтому нужен домен с A-записью на
IP сервера. У нас — поддомен `gorky.po-bvi.ru`. Бесплатные `sslip.io` / `nip.io` в России блокируются
провайдерами (соединение есть, ответа нет), их не используем.

В `.env` на сервере:

```
WEBAPP_DOMAIN=gorky.po-bvi.ru
```

Порты 80 и 443 должны быть открыты (`ufw allow 80,443/tcp`, если включён ufw).
Без `WEBAPP_DOMAIN` бот работает полностью, просто без кнопки «Календарь».

## 3б. HTTPS через существующий nginx (порты 80/443 заняты другим проектом)

Свой Caddy не запускаем. Бот слушает `127.0.0.1:18080`, nginx отдаёт наружу только наш домен —
остальные сайты на сервере не затрагиваются.

```bash
echo 'REVERSE_PROXY=nginx' >> .env                     # deploy.sh не будет поднимать Caddy
docker compose rm -sf caddy                            # если Caddy уже пытался стартовать
./scripts/deploy.sh

cp deploy/nginx-gorky.conf /etc/nginx/sites-available/gorky
ln -s /etc/nginx/sites-available/gorky /etc/nginx/sites-enabled/gorky
nginx -t && systemctl reload nginx                     # reload — без остановки работающих сайтов

certbot --nginx -d gorky.po-bvi.ru             # сертификат только для нашего домена
```

Если на сервере нет каталога `sites-enabled`, файл кладётся в `/etc/nginx/conf.d/gorky.conf`.
Если нет certbot: `apt install -y certbot python3-certbot-nginx`.

## 3а. Если хостинг блокирует Telegram

Признак — в `docker compose logs bot` ошибка `TelegramNetworkError: Request timeout error`. Проверка:
`curl -s -o /dev/null -w "%{http_code}\n" --max-time 15 https://api.telegram.org` даёт `000`.

Решение — пустить только запросы к Telegram через VPN (VLESS, например подписка Happ). На сервере:

```bash
python3 scripts/vless_to_xray.py 'https://ссылка-подписки' --list   # список серверов
python3 scripts/vless_to_xray.py 'https://ссылка-подписки' --index 1  # создаёт xray/config.json
echo 'TELEGRAM_PROXY=socks5://xray:1080' >> .env
./scripts/deploy.sh                                                   # поднимет и xray
```

Ссылку подписки берём в Happ (поделиться/скопировать подписку). Это секрет: `xray/config.json` в
`.gitignore`, в чат и git не отправлять. GigaChat и база ходят напрямую, через прокси — только Telegram.

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
