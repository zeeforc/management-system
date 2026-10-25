# Digital Product Rental Monitoring System

Internal web application and Telegram bot for managing digital product rentals, customers, renewals, manual payments, audit history, and H-5/H-3/H-1 expiration reminders.

## Architecture

- **Backend:** Python, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic
- **Web:** Vue 3, Vite, TypeScript, Tailwind CSS
- **Telegram:** aiogram 3
- **Background jobs:** Celery, Redis, PostgreSQL-backed notification/outbox records
- **Database:** PostgreSQL 16; `NUMERIC` for currency and `DATE` for rental calendar dates
- **Production edge:** Caddy HTTPS reverse proxy; Nginx serves the built Vue SPA
- **Timezone/currency:** Asia/Jakarta (WIB), IDR

PostgreSQL is the source of truth. The web UI, bot, and background workers use the same backend services and database.

## Project Structure

```text
.
├── backend/
│   ├── app/
│   │   ├── core/            # Runtime config, authentication, logging, error handling
│   │   ├── db/              # SQLAlchemy, Alembic migrations, initial owner seeder
│   │   ├── modules/         # Auth, products, customers, rentals, renewals, payments,
│   │   │                    # notifications, Telegram, audit, reports
│   │   ├── shared/          # Enums, WIB rules, money, pagination
│   │   └── workers/         # Celery app and periodic scheduler
│   └── tests/               # Unit, database integration, and end-to-end test areas
├── frontend-new/            # Vue 3 + Vite SPA, Nginx production image
├── infra/Caddyfile          # TLS reverse proxy
├── docker-compose.yml       # Web, API, bot, worker, scheduler, PostgreSQL, Redis, Caddy
├── .env.example
└── built-rules.md           # Product and technical requirements
```

## Local Development

1. Copy `.env.example` to `.env` and set local database credentials and a Telegram bot token if exercising bot delivery.
2. Start local infrastructure:

   ```powershell
   docker compose up -d postgres redis
   ```

3. Run the backend:

   ```powershell
   Set-Location backend
   .venv\Scripts\python -m pip install -e ".[dev]"
   .venv\Scripts\python -m alembic upgrade head
   .venv\Scripts\python -m app.db.seed
   .venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
   ```

4. Run the Vue frontend in another terminal:

   ```powershell
   Set-Location frontend-new
   npm ci
   npm run dev
   ```

   Vite uses its development proxy for `/api`; the default local web address is `http://localhost:5173` (or the next free port).

## Telegram Bot and Reminder Configuration

Configure these values in `.env` before running bot/worker/scheduler services:

- `TELEGRAM_BOT_TOKEN`: token from BotFather; keep it server-side.
- `TELEGRAM_ADMIN_USER_IDS`: JSON array of numeric Telegram user IDs allowed to use administrator commands, e.g. `[123456789]`.
- `TELEGRAM_LINK_TOKEN_EXPIRE_MINUTES`: lifetime of customer account-link tokens.
- `DEFAULT_REMINDER_SEND_HOUR_WIB` and `DEFAULT_REMINDER_SEND_MINUTE_WIB`: daily H-5/H-3/H-1 reminder scan time.
- `DEFAULT_OFFER_EXPIRE_HOURS`: lifetime of customer renewal offers.

Customers need both a linked Telegram private chat and recorded notification consent before reminders can be sent. Customer choice of a renewal offer does not approve a renewal or verify payment.

### Link and consent

1. Create a one-time link token from the customer record in the web app (or `POST /api/v1/customers/{customer_id}/telegram-link-token`).
2. Send the returned `deep_link_command` to the customer. The customer opens a private chat with the bot and sends `/start link_<token>`.
3. The customer sends `/consent` to opt into expiration reminders and renewal-offer messages. `/stop` revokes both consents; `/help` lists customer commands.

Tokens expire and can only be used once. The bot must be able to initiate a private conversation, so a customer must start the bot themselves.
In the web app, use **Customers → Tautkan Telegram** to generate and copy the one-time command; use **Renewal** to manage offers, approvals, and payments, and **Notifikasi** to inspect reminder delivery attempts.

### Reminder, renewal, and admin commands

The scheduler scans every five minutes and queues due H-5/H-3/H-1 reminders for the configured 09:00 WIB send time. The PostgreSQL notification and outbox rows are authoritative; Redis/Celery carry work. Delivery revalidates rental version, customer link, status, and current consent. Attempts and Telegram message IDs are recorded. Retry-after responses are retried with a bounded delay/attempt count; permanent failures are surfaced, and uncertain network outcomes remain `AMBIGUOUS` rather than being resent automatically.

Administrators can create a renewal offer for a rental. Offers appear as buttons in an eligible reminder only when the customer also consented to renewal offers. Selecting an offer creates a pending request; it never changes the rental or marks payment paid. The admin reviews the request, approves it with a renewal model and (when needed) confirmed start date, records and verifies payment, then completes the renewal. Completion requires verified payments to cover the agreed price, increments `expiration_version`, preserves sent reminder history, cancels stale pending reminders, and schedules the new expiration reminders.

Telegram administrator commands (numeric administrator IDs are allowlisted in `TELEGRAM_ADMIN_USER_IDS`):

```text
/dashboard
/products [page]
/rentals [page]
/expiring H5|H3|H1 [page]
/expired [page]
/customer <name-or-username> [page]
/help
```

The web application remains the primary review/payment interface; bot commands provide quick read-only business summaries and lists.

Telegram sends are not transactionally atomic with PostgreSQL. If the API outcome is uncertain, the system records `AMBIGUOUS` and does not retry automatically, avoiding indefinite duplicate sends while making the uncertainty visible to administrators.

## Production Deployment (Docker Compose)

Do not deploy with the sample credentials. Set `.env` values first:

- `APP_ENV=production`, `DEBUG=false`.
- A unique `SECRET_KEY` of at least 32 characters.
- Non-default `INITIAL_OWNER_PASSWORD` and PostgreSQL password.
- A real Telegram token and real numeric Telegram administrator IDs.
- `DOMAIN` to a DNS name pointing to the VPS public IP.

The API, bot, worker, and scheduler refuse known default credentials in production mode. PostgreSQL, Redis, and the API host ports bind to loopback; standalone deployments publish Caddy on ports 80/443.

After DNS and firewall setup:

```powershell
docker compose config --quiet
docker compose up -d --build
docker compose --profile bootstrap run --rm seed
docker compose ps
```

The migration service runs before API/bot/worker/scheduler startup. The `seed` profile creates the initial OWNER account idempotently. Keep the `.env` file private and do not commit it. Never run `docker compose down -v` on a production host.

### Existing CloudPanel VPS

Do not publish this stack on ports 80/443 when CloudPanel already serves other sites. Create a separate CloudPanel site for a dedicated subdomain, point its DNS A record to the VPS, and configure its HTTPS virtual host to reverse-proxy to `http://127.0.0.1:18080`. In the private `.env`, set `DOMAIN` to that subdomain, `CADDYFILE_PATH=./infra/Caddyfile.cloudpanel`, `CADDY_HTTP_BIND=127.0.0.1:18080`, `CADDY_HTTPS_BIND=127.0.0.1:18443`, `POSTGRES_PUBLISH_PORT=15432`, `REDIS_PUBLISH_PORT=16379`, and `API_PUBLISH_PORT=18000`. The CloudPanel Caddyfile serves HTTP only because CloudPanel terminates TLS. Use a unique Compose project name (for example, `-p management-system`) so container and network names remain isolated. Do not edit or restart existing CloudPanel sites or other Compose projects as part of this setup.

Before any production release:

1. Verify a recent database backup and a restore procedure.
2. Run the automated tests and review pending migrations.
3. Build and deploy containers, then check `/health/ready`, `/docs` as appropriate, and bot/worker/scheduler logs.
4. Test a reminder/renewal flow with an authorized test customer and consent.
5. Keep the previous image/version and database backup available for rollback.

VPS deployment requires the operator's DNS name and SSH access to the intended host. Do not send private keys or passwords in chat; use an SSH key already installed on the deployment machine.

## Validation

```powershell
Set-Location backend
.venv\Scripts\python -m pytest

Set-Location ..\frontend-new
npm run build
```

For the complete acceptance criteria, see [built-rules.md](./built-rules.md).
