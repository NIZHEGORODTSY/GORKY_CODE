# PostgreSQL на VPS

Боту нужна база `gorky` и пользователь `gorky`. Таблицы вручную создавать не нужно — их создают
миграции (`alembic upgrade head`), они запускаются автоматически при старте бота.

Есть два способа. **Рекомендуется первый** — он уже настроен в `docker-compose.yml`.

---

## Способ 1. Postgres в Docker (рекомендуется)

Postgres поднимается в контейнере вместе с ботом. Отдельно ничего ставить не нужно.

### 1. Подключиться к серверу и поставить Docker

```bash
ssh <user>@<ip-сервера>
curl -fsSL https://get.docker.com | sh
```

### 2. Скачать проект и положить настройки

```bash
git clone https://github.com/NIZHEGORODTSY/GORKY_CODE.git
cd GORKY_CODE
```

С **локального** компьютера скопировать прод-настройки (в них пароль базы, токены):

```bash
scp .env.prod <user>@<ip-сервера>:~/GORKY_CODE/.env
```

В `.env` за базу отвечают строки (пароль уже сгенерирован):

```
POSTGRES_USER=gorky
POSTGRES_PASSWORD=<пароль>
POSTGRES_DB=gorky
DATABASE_URL=postgresql+asyncpg://gorky:<пароль>@db:5432/gorky
```

Хост в `DATABASE_URL` — `db`: так бот находит контейнер с базой внутри docker compose.

### 3. Запустить

```bash
./scripts/deploy.sh
```

Docker сам создаст пользователя и базу из переменных `POSTGRES_*`, бот при старте применит миграции.
Данные хранятся в томе `pgdata` и переживают перезапуски и обновления.

### 4. Проверить

```bash
docker compose ps                                    # db — healthy, bot — running
docker compose exec db psql -U gorky -d gorky -c '\dt'   # таблицы users, events, alembic_version
```

---

## Способ 2. Postgres прямо на сервере (без Docker)

Подходит, если бот тоже запускается без Docker (через `python -m app.main`).

### 1. Установить PostgreSQL 16 (Ubuntu 22.04 / 24.04)

```bash
sudo apt update
sudo apt install -y postgresql-common
sudo /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y   # официальный репозиторий PostgreSQL
sudo apt install -y postgresql-16
sudo systemctl enable --now postgresql
```

### 2. Создать пользователя и базу

Придумай пароль (или сгенерируй: `openssl rand -base64 18`) и подставь вместо `<пароль>`:

```bash
sudo -u postgres psql -c "CREATE ROLE gorky LOGIN PASSWORD '<пароль>';"
sudo -u postgres psql -c "CREATE DATABASE gorky OWNER gorky;"
```

### 3. Доступ только с самого сервера

По умолчанию Postgres слушает только `localhost` — так и оставляем, наружу порт 5432 не открываем.
Проверить:

```bash
sudo -u postgres psql -tAc "SHOW listen_addresses;"   # должно быть localhost
```

### 4. Настройки бота

В `.env` на сервере:

```
DATABASE_URL=postgresql+asyncpg://gorky:<пароль>@localhost:5432/gorky
```

### 5. Миграции и проверка

```bash
cd ~/GORKY_CODE
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
.venv/bin/alembic upgrade head
psql "postgresql://gorky:<пароль>@localhost:5432/gorky" -c '\dt'
```

---

## Смотреть базу с компьютера (pgAdmin)

Порт базы наружу закрыт, поэтому подключаемся через SSH-туннель. На **локальном** компьютере:

```bash
ssh -N -L 5433:127.0.0.1:5433 root@89.111.136.194   # способ 1 (Docker): база на сервере на порту 5433
ssh -N -L 5433:127.0.0.1:5432 root@89.111.136.194   # способ 2 (без Docker): обычный порт 5432
```

Пока команда работает, в pgAdmin: **Register → Server**, Host `localhost`, Port `5433`,
Username `gorky`, Password — из `.env` на сервере. (Локально 5433, чтобы не конфликтовать с
Postgres на компьютере.)

В Docker база слушает на сервере порт **5433** (`DB_HOST_PORT` в `.env`), чтобы не конфликтовать
с Postgres, если он установлен на сервере отдельно.

## Бэкап и восстановление

Docker:

```bash
docker compose exec db pg_dump -U gorky gorky > backup_$(date +%F).sql
docker compose exec -T db psql -U gorky gorky < backup_2026-10-30.sql
```

Без Docker:

```bash
pg_dump "postgresql://gorky:<пароль>@localhost:5432/gorky" > backup_$(date +%F).sql
psql "postgresql://gorky:<пароль>@localhost:5432/gorky" < backup_2026-10-30.sql
```

Ежедневный бэкап в 3:00 (Docker), `crontab -e`:

```
0 3 * * * cd ~/GORKY_CODE && docker compose exec -T db pg_dump -U gorky gorky > ~/backups/gorky_$(date +\%F).sql
```

(перед этим `mkdir -p ~/backups`)

## Если что-то не так

| Симптом | Что проверить |
|---|---|
| `password authentication failed` | пароль в `DATABASE_URL` совпадает с `POSTGRES_PASSWORD` / паролем роли |
| бот не видит базу в Docker | хост в `DATABASE_URL` — `db`, а не `localhost` |
| бот не видит базу без Docker | `sudo systemctl status postgresql`, хост — `localhost` |
| сменил `POSTGRES_PASSWORD`, а пароль старый | Docker создаёт пользователя только при первом запуске тома; поменять: `docker compose exec db psql -U gorky -c "ALTER ROLE gorky PASSWORD '<новый>';"` |
| нет таблиц | `docker compose logs bot` — ошибка миграций при старте |
