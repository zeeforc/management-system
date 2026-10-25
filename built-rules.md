# DIGITAL PRODUCT RENTAL MONITORING SYSTEM
## Final Software Requirements & Technical Architecture Specification

**Document version:** 1.1  
**Project type:** Internal Web Application + Telegram Bot  
**Backend:** Python + FastAPI  
**Frontend:** Next.js + TypeScript  
**Database:** PostgreSQL  
**ORM:** SQLAlchemy 2.x  
**Migration:** Alembic  
**Bot:** aiogram 3.x  
**Background processing:** Celery + Redis  
**Deployment:** Docker Compose on Linux VPS  
**Business timezone:** Asia/Jakarta  
**Currency:** IDR  
**Architecture:** Modular Monolith + Background Workers

---

# 1. PROJECT OBJECTIVE

Develop a production-ready Digital Product Rental Monitoring System to manage digital product rentals, customer records, rental expiration dates, renewal offers, payments, and Telegram notifications.

The application must provide:

1. A web dashboard for centralized business management.
2. Product and variant management.
3. Customer management with Telegram account linking.
4. Rental lifecycle and expiration monitoring.
5. Automated H-5, H-3, and H-1 expiration reminders.
6. Telegram renewal offers with selectable duration and price.
7. Manual payment recording and verification.
8. Continuous and immediate renewal models.
9. A Telegram Bot interface for administrator operations.
10. Notification logs, audit history, reports, backups, and operational monitoring.

The system must be maintainable, secure, extensible, and reliable when the number of customers and rental transactions grows.

The initial release is an internal business application. Automated payment gateway processing, public customer registration, and automatic third-party account provisioning are outside the mandatory initial scope.

# 2. ARCHITECTURAL DECISIONS

## 2.1 Modular Monolith

Use a modular monolith for the primary backend instead of microservices.

A modular monolith means that the application is deployed as one backend codebase, but its business responsibilities are separated into independent modules with clearly defined interfaces.

Required modules:

- Authentication and authorization.
- Product catalog.
- Product variants.
- Customer management.
- Telegram identity linking.
- Rental management.
- Renewal management.
- Payment management.
- Notification scheduling.
- Telegram Bot integration.
- Reporting and analytics.
- Audit logging.
- System configuration.

Each module must own its business rules and expose service interfaces for other modules.

Avoid circular dependencies and direct access to another module's internal implementation.

The website API, Telegram Bot handlers, and background workers must invoke the same application services. They must not implement their own competing versions of rental calculations or payment rules.

## 2.2 Single Source of Truth

PostgreSQL is the authoritative source for business data.

The following components must use the same backend business services and database:

- Website frontend.
- FastAPI backend.
- Telegram Bot.
- Background workers.
- Scheduler.

Redis is used for background job coordination and temporary queue data, not as the permanent storage for rental, renewal, payment, or audit records.

Do not maintain separate business databases for the website and Telegram Bot.

## 2.3 Deployment Topology

The initial production deployment must support the following services:

- `web`: Next.js frontend.
- `api`: FastAPI backend.
- `bot`: Telegram Bot process.
- `worker`: background job processor.
- `scheduler`: periodic scheduling process.
- `postgres`: primary database.
- `redis`: queue and coordination service.
- `proxy`: HTTPS reverse proxy.

Services may use the same application image with different entry points when appropriate.

Do not introduce Kubernetes, multiple independently deployed microservices, or other operationally complex infrastructure unless a documented scaling requirement justifies it.

The architecture must allow additional API workers and background workers to be added later without changing business logic.

# 3. TECHNOLOGY AND CODE STANDARDS

Use:

- Python with FastAPI.
- PostgreSQL.
- SQLAlchemy 2.x.
- Alembic.
- Pydantic.
- aiogram 3.x.
- Celery and Redis.
- Next.js and TypeScript.
- pytest.
- Docker Compose.
- Git-based version control.
- Automated linting and type checking.

Use asynchronous database operations only where supported and justified by the application architecture. Do not mix synchronous and asynchronous database sessions incorrectly.

Pin compatible dependency versions and maintain a tested dependency upgrade process.

The codebase must include:

- Consistent naming conventions.
- Type annotations.
- Explicit transaction boundaries.
- Centralized validation and error handling.
- Structured logging.
- Configuration management.
- Automated tests.
- Documentation for non-obvious business rules.

Secrets must be provided through environment configuration or an appropriate secrets manager.

# 4. RECOMMENDED PROJECT STRUCTURE

Use a feature-oriented backend structure similar to the following:

    backend/
      app/
        main.py

        core/
          config.py
          security.py
          exceptions.py
          logging.py
          permissions.py

        db/
          session.py
          base.py
          migrations/

        modules/
          auth/
            models.py
            schemas.py
            repository.py
            service.py
            router.py

          products/
            models.py
            schemas.py
            repository.py
            service.py
            router.py

          customers/
            models.py
            schemas.py
            repository.py
            service.py
            router.py

          rentals/
            models.py
            schemas.py
            repository.py
            service.py
            router.py

          renewals/
            models.py
            schemas.py
            repository.py
            service.py
            router.py

          payments/
            models.py
            schemas.py
            repository.py
            service.py
            router.py

          notifications/
            models.py
            schemas.py
            repository.py
            service.py
            router.py
            tasks.py

          telegram/
            handlers/
            keyboards.py
            callbacks.py
            service.py

          audit/
            models.py
            service.py

          reports/
            service.py
            router.py

        shared/
          enums.py
          datetime_utils.py
          money.py
          pagination.py

        workers/
          celery_app.py
          scheduled_tasks.py

      tests/
        unit/
        integration/
        e2e/

      alembic.ini
      pyproject.toml
      Dockerfile

    frontend/
      src/
        app/
        components/
        features/
        lib/
        hooks/
        types/

    docker-compose.yml
    .env.example
    README.md

This structure is a reference architecture, not a requirement to create empty files for every possible component.

Create modules only when they contain meaningful functionality. Keep database queries in repositories, business rules in services, and HTTP-specific behavior in API routers.

# 5. DATABASE DESIGN PRINCIPLES

The database must be normalized, relational, and designed around business entities rather than individual screens.

Mandatory principles:

1. Use UUID primary keys for internal business entities where appropriate.
2. Use foreign keys to preserve referential integrity.
3. Use unique constraints for identifiers that must not be duplicated.
4. Use database transactions for related business changes.
5. Use indexes based on real query patterns.
6. Store money using PostgreSQL `NUMERIC`, never floating-point types.
7. Store calendar rental dates as PostgreSQL `DATE` where appropriate.
8. Store event timestamps using timezone-aware timestamps.
9. Keep historical prices and durations as transaction snapshots.
10. Archive historical business entities instead of cascading deletion.
11. Use explicit status transitions and validation.
12. Record important administrative changes in audit logs.
13. Avoid storing calculated dashboard totals as independent authoritative data.
14. Use database constraints for critical invariants wherever possible.
15. Introduce schema changes through Alembic migrations.

Do not use JSON fields as a substitute for normal relational tables when the data has stable fields, relationships, or integrity requirements.

JSONB is acceptable for flexible audit snapshots, structured error details, and metadata that does not require ordinary relational constraints.

# 6. DATABASE ENTITY DESIGN

## 6.1 Administrator and roles

### `admin_users`

Fields:

- `id`: UUID primary key.
- `email`: unique.
- `password_hash`.
- `is_active`.
- `last_login_at`.
- `created_at`.
- `updated_at`.

### `roles`

Fields:

- `id`.
- `name`: unique.
- `description`.

### `user_roles`

Fields:

- `user_id`.
- `role_id`.

Use a composite primary key or unique constraint on the role assignment.

The first release may use only the Owner role. The schema must support future staff roles without redesigning authentication.

## 6.2 Products

### `products`

Fields:

- `id`.
- `name`.
- `description`.
- `category`.
- `image_url`.
- `status`.
- `created_at`.
- `updated_at`.
- `archived_at`, nullable.

### `product_variants`

Fields:

- `id`.
- `product_id`.
- `name`.
- `duration_value`.
- `duration_unit`.
- `default_price`.
- `currency`.
- `status`.
- `created_at`.
- `updated_at`.
- `archived_at`, nullable.

Use a foreign key from `product_variants.product_id` to `products.id`.

Variant duration units must have explicitly defined meanings: days, weeks, calendar months, or calendar years.

Historical rentals must retain their original duration and price even if a variant changes later.

## 6.3 Customers and Telegram identities

### `customers`

Fields:

- `id`.
- `display_name`.
- `telegram_username`, nullable.
- `telegram_user_id`, nullable.
- `telegram_chat_id`, nullable.
- `status`.
- `internal_notes`.
- `created_at`.
- `updated_at`.
- `archived_at`, nullable.

Store Telegram numeric identifiers using a sufficiently large integer type, such as PostgreSQL `BIGINT`, after verifying the identifier requirements.

Apply appropriate uniqueness constraints to linked Telegram identities.

Usernames are mutable and must not serve as permanent customer keys.

### `notification_consents`

Fields:

- `id`.
- `customer_id`.
- `consent_type`.
- `consent_status`.
- `source`.
- `consented_at`.
- `revoked_at`.
- `created_at`.

Retain consent history rather than replacing the previous record without an audit trail.

A customer must have a linked Telegram private chat and valid consent before automated private messages can be sent.

### `telegram_link_tokens`

Fields:

- `id`.
- `customer_id`.
- `token_hash`.
- `expires_at`.
- `used_at`.
- `created_at`.

Generate cryptographically random linking tokens, store only their hashes when feasible, enforce expiration, and permit each token to be used once.

## 6.4 Rentals

### `rentals`

Fields:

- `id`.
- `customer_id`.
- `product_id`.
- `product_variant_id`.
- `start_date`.
- `expiration_date`.
- `duration_value`.
- `duration_unit`.
- `agreed_price`.
- `currency`.
- `status`.
- `renewal_model`.
- `created_by`.
- `created_at`.
- `updated_at`.
- `archived_at`, nullable.

Store product and variant relationships for reporting, while snapshotting the agreed duration and price.

The expiration date must be greater than or equal to the start date.

Use an explicit status model for Scheduled, Active, Expiring Soon, Expired, and Cancelled.

Treat Expiring Soon as a derived warning state where practical, rather than relying on a stale stored status.

## 6.5 Renewal transactions

### `rental_renewals`

Fields:

- `id`.
- `rental_id`.
- `previous_start_date`.
- `previous_expiration_date`.
- `new_start_date`.
- `new_expiration_date`.
- `duration_value`.
- `duration_unit`.
- `renewal_model`.
- `agreed_price`.
- `currency`.
- `status`.
- `created_by`.
- `completed_at`.
- `created_at`.

A renewal record must preserve the before-and-after rental information.

Use an explicit renewal status model, including Pending, Approved, Completed, Rejected, and Cancelled as appropriate.

Only a completed renewal may change the effective rental dates.

## 6.6 Renewal offers

### `renewal_offers`

Fields:

- `id`.
- `rental_id`.
- `customer_id`.
- `offered_duration_value`.
- `offered_duration_unit`.
- `offered_price`.
- `currency`.
- `renewal_model`.
- `status`.
- `expires_at`.
- `selected_at`.
- `created_at`.

The offered duration, price, and terms must be snapshots.

Customer selection must reference the exact offer that was displayed.

Expired or invalid offers must not be accepted.

## 6.7 Payments

### `payments`

Fields:

- `id`.
- `customer_id`.
- `rental_id`.
- `renewal_id`, nullable where appropriate.
- `amount`.
- `currency`.
- `payment_method`.
- `status`.
- `payment_reference`, nullable.
- `paid_at`, nullable.
- `verified_at`, nullable.
- `verified_by`, nullable.
- `created_at`.
- `updated_at`.

Use `NUMERIC` for money and validate currency consistency.

A payment record must not be treated as verified merely because it was created or because the customer selected a renewal offer.

Support Pending, Paid, Failed, Cancelled, Refunded, and Partially Paid states according to the documented payment model.

If partial payments are supported, calculate the outstanding balance using the authoritative set of valid payment and refund transactions.

For a future payment gateway, add a separate payment-attempt or provider-event entity rather than overloading the manual payment fields.

## 6.8 Notifications

### `notifications`

Fields:

- `id`.
- `rental_id`.
- `customer_id`.
- `reminder_stage`.
- `expiration_version`.
- `scheduled_at`.
- `status`.
- `attempt_count`.
- `sent_at`.
- `telegram_message_id`, nullable.
- `last_error`, nullable.
- `created_at`.
- `updated_at`.

Represent reminder stages explicitly: H5, H3, and H1.

The expiration version must change whenever a rental expiration changes, or an equivalent versioning mechanism must be implemented.

Create a uniqueness constraint for the business key representing a specific rental, expiration version, and reminder stage.

The exact constraint must account for the selected data model and must prevent duplicate scheduling for the same reminder stage and expiration version.

## 6.9 Notification attempts

### `notification_attempts`

Fields:

- `id`.
- `notification_id`.
- `attempt_number`.
- `started_at`.
- `finished_at`.
- `result_status`.
- `telegram_message_id`, nullable.
- `error_code`, nullable.
- `error_summary`, nullable.

This table preserves individual delivery attempts and their outcomes.

Do not store Bot tokens, linking tokens, or sensitive customer data in error messages.

## 6.10 Customer responses

### `notification_responses`

Fields:

- `id`.
- `notification_id`, nullable.
- `rental_id`.
- `customer_id`.
- `renewal_offer_id`, nullable.
- `response_type`.
- `responded_at`.
- `created_at`.

Store the exact response and the relevant offer or notification reference.

Validate that the response belongs to the customer associated with the offer and rental.

## 6.11 Transactional outbox

### `outbox_events`

Fields:

- `id`.
- `event_type`.
- `aggregate_type`.
- `aggregate_id`.
- `payload`.
- `status`.
- `attempt_count`.
- `available_at`.
- `processed_at`.
- `last_error`.
- `created_at`.

Use this table to record important events that must be processed asynchronously.

Examples:

- Rental created.
- Rental renewed.
- Renewal request created.
- Payment verified.
- Expiration reminders recalculated.
- Customer notification requested.

The business change and its outbox event must be committed in the same PostgreSQL transaction.

A background dispatcher reads pending outbox events, publishes or processes them, and marks them as processed only after the corresponding work has been safely recorded.

Outbox processing must be idempotent because the same event may be encountered again after a worker failure.

## 6.12 Idempotency keys

### `idempotency_records`

Fields:

- `id`.
- `scope`.
- `idempotency_key`.
- `request_hash`.
- `response_status`, nullable.
- `response_reference`, nullable.
- `created_at`.
- `expires_at`, nullable.

Apply a unique constraint to the appropriate scope and idempotency key.

Use this mechanism for duplicate-sensitive operations such as renewal creation, payment submissions, and webhook or callback processing where appropriate.

The same key with a different request payload must be rejected rather than silently returning an unrelated result.

## 6.13 Audit logs

### `audit_logs`

Fields:

- `id`.
- `actor_type`.
- `actor_id`, nullable.
- `action`.
- `entity_type`.
- `entity_id`.
- `before_data`, nullable.
- `after_data`, nullable.
- `request_id`, nullable.
- `created_at`.

Audit sensitive administrative actions, including:

- Rental date changes.
- Renewal approval and completion.
- Payment verification.
- Refunds and corrections.
- Customer consent changes.
- Product and pricing changes.
- Administrative account changes.

Audit logs must not contain passwords, secrets, Bot tokens, or complete sensitive payment credentials.

## 6.14 System settings

### `system_settings`

Fields:

- `key`.
- `value`.
- `updated_by`.
- `updated_at`.

Use a unique key for each setting.

Appropriate settings include timezone, reminder sending times, enabled reminder stages, offer expiration duration, and message templates.

Never store production secrets in ordinary settings values.

---

# 7. DATABASE RELATIONSHIPS AND INDEXES

The entity relationships must follow these rules:

- One product has many variants.
- One customer has many rentals.
- One rental references one customer, one product, and one product variant.
- One rental has many renewal records.
- One rental can have multiple renewal offers.
- One renewal transaction can have multiple related payment records where required.
- One rental has many notification records.
- One notification can have multiple notification attempts.
- Customer responses reference the relevant customer, rental, and offer.
- Outbox events reference the business aggregate that generated them.
- Audit records identify the actor and affected entity where possible.

Recommended indexes include:

- `rentals(expiration_date, status)`.
- `rentals(customer_id, expiration_date)`.
- `rentals(product_id, status)`.
- `rentals(product_variant_id, status)`.
- `notifications(status, scheduled_at)`.
- `notifications(rental_id, expiration_version, reminder_stage)`, with the appropriate unique constraint.
- `renewal_offers(customer_id, status, expires_at)`.
- `payments(status, created_at)`.
- `payments(rental_id)`.
- `outbox_events(status, available_at)`.
- `audit_logs(entity_type, entity_id, created_at)`.
- Unique indexes for linked Telegram identifiers where applicable.

Do not add indexes indiscriminately. Validate important indexes against actual queries using PostgreSQL query plans.

Use `EXPLAIN ANALYZE` in a safe test environment to investigate expensive queries.

Avoid loading every customer or rental into application memory for dashboard summaries.

Use database-side aggregation, server-side filtering, and pagination.

# 8. TRANSACTION AND DATA INTEGRITY DESIGN

Every business operation that modifies multiple related records must define its transaction boundary.

## 8.1 Completing a renewal

The renewal service must:

1. Begin a database transaction.
2. Lock the relevant rental or otherwise prevent conflicting concurrent updates.
3. Validate the current rental state.
4. Validate the selected renewal request and offer.
5. Validate the applicable payment requirements.
6. Calculate the new dates using the selected renewal model.
7. Create the renewal history record.
8. Update the effective rental dates.
9. Mark the renewal as completed.
10. Invalidate obsolete offers.
11. Create or update reminder scheduling records.
12. Insert an outbox event for any required downstream processing.
13. Commit the transaction.

If any mandatory operation fails before commit, the transaction must roll back.

Do not call Telegram APIs while holding a database transaction open.

Any outbound messages must be processed after the business transaction has committed.

## 8.2 Verifying a payment

The payment verification service must:

1. Confirm the administrator has permission to verify payments.
2. Load the payment and associated transaction.
3. Validate the current payment state.
4. Prevent duplicate verification.
5. Record the verified amount and timestamp.
6. Record the verifying administrator.
7. Update the applicable payment or renewal state.
8. Create an outbox event if further processing is needed.
9. Write the audit event.
10. Commit all related database changes transactionally.

A verified payment must not automatically extend a rental unless the corresponding renewal requirements are also satisfied and the renewal service completes the operation.

## 8.3 Duplicate requests

The system must handle duplicate requests caused by:

- Double-clicks.
- Browser retries.
- Telegram callback retries.
- Worker restarts.
- Network timeouts.
- Concurrent administrator actions.

Use idempotency keys, unique constraints, database transactions, and locking as appropriate.

Do not rely exclusively on frontend button disabling to prevent duplicates.

# 9. RENTAL DATE AND STATUS RULES

## 9.1 Business timezone

Use Asia/Jakarta for all business-calendar calculations.

Store event timestamps consistently using UTC-aware timestamps in PostgreSQL. Convert timestamps to WIB for presentation and scheduled business operations.

Store rental start and expiration dates as `DATE` when the contract is defined by calendar dates.

## 9.2 Inclusive expiration date

The expiration date is inclusive.

For a rental expiring on 29 October:

- Valid through 29 October.
- Expired starting 30 October in Asia/Jakarta.

The implementation must use one shared date-calculation service for the website, Bot, scheduler, and reports.

## 9.3 Duration calculations

The system must explicitly define how calendar months and years are calculated.

For example, adding one calendar month to 31 January must use a documented rule for months without the 31st. A recommended rule is to clamp the result to the last valid day of the target month.

All interfaces must use the same calculation service.

## 9.4 Renewal models

Support:

**Continuous renewal:** for an unexpired rental, the new period begins on the day after the previous expiration date.

**Immediate renewal:** the new period begins on an explicitly confirmed start date.

For an expired rental, require an explicit new start date.

Never silently infer a renewal start date.

## 9.5 Derived status

Rental lifecycle status and expiration warning state must remain separate concepts.

The system may calculate the current warning state from:

- Rental lifecycle status.
- Current WIB date.
- Expiration date.
- Configured reminder window.

The dashboard must not rely on a stale background-updated status to determine whether a rental is actually expired.

# 10. NOTIFICATION SCHEDULING ARCHITECTURE

## 10.1 Reminder stages

Required stages:

- H-5.
- H-3.
- H-1.

Default sending time: 09:00 WIB, configurable.

A rental expiring on 29 October has reminder dates of 24 October, 26 October, and 28 October.

## 10.2 Persistent scheduling

The system must persist reminder scheduling state in PostgreSQL.

Redis and Celery may be used to execute jobs, but PostgreSQL must remain the authoritative source for whether a reminder exists, is eligible, has been sent, or has failed.

The scheduler must be safe to restart and must not depend on an administrator keeping the website open.

## 10.3 Reminder dispatch flow

The implementation should follow this sequence:

1. Identify rentals with upcoming reminder dates.
2. Validate current rental state.
3. Validate customer notification consent.
4. Validate the linked Telegram chat.
5. Create or locate the unique notification record.
6. Commit the notification record and any associated outbox event.
7. Queue the notification for processing.
8. Revalidate eligibility immediately before sending.
9. Call the Telegram Bot API.
10. Record the API result and attempt details.
11. Mark the notification as Sent only after the API accepts the send request.
12. Schedule retries for retryable failures.
13. Surface permanent failures to the administrator.

Never mark a notification Sent before receiving a successful Telegram API response.

## 10.4 Exactly-once limitations

Telegram message sending and PostgreSQL transactions cannot be combined into one atomic transaction.

If the Telegram API accepts a message but the worker crashes before saving the successful result, the system may not know whether the message was sent.

Therefore, the implementation must not claim absolute exactly-once delivery.

Use idempotent database operations, persistent jobs, bounded retries, and explicit handling of ambiguous send outcomes to minimize duplicate messages.

Where the outcome is uncertain, the system must follow a documented recovery policy instead of retrying indefinitely.

## 10.5 Expiration changes

When a rental is renewed or its expiration date changes:

- Increment the expiration version or invalidate the previous scheduling generation.
- Cancel pending reminders for the old expiration.
- Prevent old queued jobs from sending.
- Recalculate H-5, H-3, and H-1 reminders.
- Preserve the history of notifications already sent.

A previously sent reminder must remain in history even if its expiration date later changes.

## 10.6 Failure handling

Retry temporary failures with bounded exponential backoff and appropriate jitter.

Do not retry permanent failures indefinitely.

Respect Telegram API rate limits and retry instructions where applicable.

Failed notifications must be visible in the dashboard and notification logs.

# 11. TELEGRAM RENEWAL OFFER FLOW

## 11.1 Message contents

A reminder must include:

- Customer greeting.
- Product and variant.
- Expiration date.
- Remaining time.
- Available renewal options.
- Price for each option.
- A decline option.

Prices and durations must be loaded from valid configured offers rather than hardcoded message templates.

## 11.2 Selecting an offer

When the customer selects a renewal option:

1. Validate the Telegram sender.
2. Validate the customer-to-chat association.
3. Validate the offer identifier.
4. Confirm the offer belongs to the customer and rental.
5. Confirm the offer has not expired or been cancelled.
6. Prevent duplicate selection processing.
7. Record the selection.
8. Create or update the pending renewal request.
9. Notify the administrator through the dashboard and optional Telegram message.
10. Confirm receipt to the customer.

Selecting an offer must not automatically activate the renewal or mark the payment as complete.

## 11.3 Declining an offer

When a customer declines:

- Record the response.
- Invalidate the relevant actionable offer if appropriate.
- Update the renewal interest state.
- Inform the customer.
- Make the response available to the administrator.

## 11.4 Administrator approval

The administrator must be able to:

- Review the selected duration and price.
- Choose the renewal model.
- Confirm the start date.
- Review payment status.
- Approve or reject the renewal request.
- Complete the renewal after payment requirements are satisfied.

# 12. WEB DASHBOARD AND TELEGRAM ADMINISTRATOR INTERFACE

## 12.1 Dashboard metrics

Display:

- Total products.
- Total active variants.
- Total customers.
- Active rentals.
- Rentals expiring in five days.
- Rentals expiring in three days.
- Rentals expiring tomorrow.
- Expired rentals.
- Pending renewal requests.
- Pending payment verification.
- Verified payment totals.
- Failed notifications.

Each metric must use a documented query and business definition.

Revenue must be calculated from verified financial records, with refunds and adjustments handled consistently.

## 12.2 Main navigation

The website must include:

- Dashboard.
- Products.
- Product Variants.
- Customers.
- Rentals.
- Expiring Soon.
- Expired Rentals.
- Renewal Requests.
- Payments.
- Notification Logs.
- Reports.
- Settings.

## 12.3 Rental detail page

Show customer information, product details, start and expiration dates, status, renewal model, payment history, offers, notification history, and available administrative actions.

## 12.4 Telegram administrator commands

Required commands:

- `/start`
- `/dashboard`
- `/products`
- `/rentals`
- `/expiring`
- `/expired`
- `/customer`
- `/help`

Restrict administrator commands using configured Telegram numeric user IDs.

Long lists must support pagination and filtering.

Customer-facing commands must never expose administrative information or another customer's data.

# 13. API DESIGN

Use versioned REST endpoints under `/api/v1`.

Required endpoint groups:

- Authentication.
- Dashboard summaries.
- Products and variants.
- Customers.
- Rentals.
- Renewal offers.
- Renewal requests.
- Payments.
- Payment verification.
- Notifications.
- Audit logs.
- System settings.
- Health checks.

Illustrative endpoints:

- `GET /api/v1/dashboard/summary`
- `GET /api/v1/rentals`
- `POST /api/v1/rentals`
- `GET /api/v1/rentals/{id}`
- `POST /api/v1/rentals/{id}/renewals`
- `POST /api/v1/renewal-offers`
- `POST /api/v1/payments`
- `POST /api/v1/payments/{id}/verify`
- `POST /api/v1/rentals/{id}/notifications`
- `GET /api/v1/notifications`
- `GET /health/live`
- `GET /health/ready`

Document the request schema, response schema, validation rules, permissions, and error codes for every endpoint.

Do not expose internal database models directly as public API contracts.

# 14. SECURITY REQUIREMENTS

Implement:

- Secure administrator authentication.
- Password hashing.
- Server-side role checks.
- Session and CSRF protections where applicable.
- Input validation.
- Rate limiting.
- HTTPS.
- Secure secrets management.
- Restricted database access.
- Telegram callback validation.
- Customer data isolation.
- Audit logging.
- Safe error responses.
- Dependency vulnerability management.

Do not store credentials in source code, frontend bundles, ordinary system settings, or logs.

Do not allow public Telegram users to invoke administrator commands.

Do not trust callback payloads, user-submitted customer IDs, or client-side role indicators without server-side verification.

# 15. TESTING STRATEGY

Use pytest for unit and integration tests.

## Unit tests

Test:

- Rental status calculations.
- Calendar-month duration calculations.
- Continuous renewal.
- Immediate renewal.
- Expiration boundaries.
- Reminder date calculations.
- Payment state transitions.
- Renewal eligibility.

## Database integration tests

Test:

- Foreign-key constraints.
- Unique constraints.
- Concurrent renewal attempts.
- Duplicate payment verification.
- Duplicate notification creation.
- Transaction rollback.
- Outbox recovery.
- Historical record preservation.

## Telegram integration tests

Use mocked Telegram API responses for automated tests.

Test:

- Customer linking.
- Consent enforcement.
- Offer selection.
- Duplicate callback processing.
- Expired offers.
- API failures.
- Retry handling.
- Ambiguous send outcomes.
- Unauthorized administrator commands.

## End-to-end tests

Verify complete scenarios from the website and Telegram Bot, including rental creation, expiration reminders, customer selection, payment verification, renewal completion, and rescheduling.

# 16. OBSERVABILITY AND MAINTENANCE

The system must provide:

- Structured application logs.
- Request correlation IDs.
- Background job status.
- Notification failure monitoring.
- Database health checks.
- Worker health checks.
- Disk-space monitoring.
- Backup status monitoring.
- Useful error messages for administrators.

Avoid logging sensitive credentials or unnecessary personal data.

Document a retention policy for notification attempts, audit logs, and other operational records.

Do not introduce a large monitoring stack unless the deployment scale justifies it. Start with structured logs, health checks, and actionable alerts.

# 17. BACKUP, MIGRATION, AND ROLLBACK

## 17.1 Database backup

Provide automated PostgreSQL backups.

The implementation must document:

- Backup frequency.
- Retention policy.
- Backup encryption where appropriate.
- Backup storage location.
- Restoration procedure.
- Backup verification.
- Recovery point objective.
- Recovery time objective.

At least one restoration test must be completed before production acceptance.

Backups must be stored separately from the primary database volume.

## 17.2 Schema migrations

All schema changes must use Alembic.

Requirements:

- Migrations are version-controlled.
- Migrations are tested against a clean database.
- Existing production data is preserved.
- Destructive migrations require explicit review.
- Rollback limitations are documented.
- Database backups are taken before risky migrations.

For changes that may affect large tables, use an expand-and-contract migration strategy where appropriate:

1. Add compatible schema changes.
2. Deploy code that supports the old and new forms.
3. Backfill data if necessary.
4. Switch application behavior.
5. Remove obsolete fields only after verification.

Do not assume every migration can be safely reversed automatically.

## 17.3 Application deployment

Production deployment must include:

1. Backup verification.
2. Application image build.
3. Test execution.
4. Migration review.
5. Database migration.
6. Service deployment.
7. Health checks.
8. Smoke tests.
9. Log review.
10. Rollback procedure if critical checks fail.

# 18. PERFORMANCE AND SCALABILITY

The initial system must prioritize correctness and maintainability over premature optimization.

Requirements:

- Server-side pagination.
- Database-side dashboard aggregation.
- Appropriate indexes.
- Connection pooling.
- Bounded background worker concurrency.
- Telegram rate-limit handling.
- Efficient database queries.
- Avoidance of N+1 query patterns.
- Timeouts for external API calls.
- Bounded retries.
- Monitoring of slow queries.

The architecture must allow the API and workers to scale horizontally without duplicating business operations.

Do not introduce read replicas, distributed caching, or microservices until actual traffic and performance measurements justify them.

# 19. DEVELOPMENT PHASES

## Phase 1 — Architecture and Foundation

Deliver:

- Approved architecture document.
- ERD and database schema.
- Defined status transitions.
- Defined date and money rules.
- Authentication.
- Product and variant modules.
- Customer module.
- Rental module.
- Initial dashboard.
- Alembic migrations.
- Unit and integration tests.

Exit condition: the database design, core relationships, and rental calculations pass review and automated tests.

## Phase 2 — Renewal and Payments

Deliver:

- Renewal models.
- Renewal offers.
- Renewal request workflow.
- Payment records.
- Payment verification.
- Transactional renewal completion.
- Audit history.
- Idempotency controls.

Exit condition: concurrent requests cannot create inconsistent or duplicate completed renewals.

## Phase 3 — Telegram Integration

Deliver:

- Dedicated Bot.
- Administrator commands.
- Customer account linking.
- Notification consent.
- Renewal selection.
- Customer response handling.

Exit condition: website and Bot operate on the same business data with proper authorization.

## Phase 4 — Background Notifications

Deliver:

- Persistent reminder schedules.
- H-5, H-3, H-1 reminders.
- Transactional outbox.
- Notification workers.
- Retry policies.
- Duplicate prevention.
- Notification logs.
- Failure alerts.

Exit condition: reminder processing recovers safely after worker restarts and handles simulated API failures correctly.

## Phase 5 — Production Readiness

Deliver:

- Security review.
- Full automated test suite.
- Production Docker configuration.
- HTTPS.
- Backups and restoration tests.
- Monitoring.
- Deployment and rollback documentation.
- Administrator guide.
- Acceptance test report.

Exit condition: all mandatory acceptance criteria pass.

# 20. DEFINITION OF DONE

A feature is complete only when:

- Business rules are implemented in the backend.
- Database changes are version-controlled.
- Data integrity is enforced.
- Authorization is tested.
- Failure scenarios are handled.
- Automated tests pass.
- Logs and audit records are available where required.
- Website and Telegram behavior are consistent.
- Documentation is updated.
- Acceptance criteria are verified.

Do not mark a feature complete merely because the UI exists or a happy-path demonstration succeeds.

# 21. FINAL ACCEPTANCE CRITERIA

The system must demonstrate that:

1. Products, variants, customers, and rentals can be managed through the website.
2. Multiple rentals per customer are supported.
3. Rental status and expiration calculations are consistent.
4. Continuous and immediate renewal both work.
5. Renewal offers contain correct duration and price snapshots.
6. Customer selection does not falsely mark a renewal as paid.
7. Payments can be recorded and verified with an audit trail.
8. H-5, H-3, and H-1 reminders are calculated correctly.
9. Notifications require valid consent and a linked Telegram chat.
10. Duplicate notifications and duplicate renewals are prevented to the extent supported by the documented processing guarantees.
11. Obsolete reminders are cancelled or invalidated after rental changes.
12. Background jobs survive restarts without losing authoritative business records.
13. Transactional outbox events are recoverable and idempotently processed.
14. Dashboard metrics match database results.
15. Unauthorized users cannot access administrative data.
16. Database migrations preserve existing data.
17. Backups can be restored successfully.
18. Deployment, monitoring, and rollback procedures are documented.

# 22. FINAL DEVELOPMENT INSTRUCTION

Before writing the production implementation, the development team must submit and obtain approval for:

1. System architecture diagram.
2. Database entity relationship diagram.
3. Final database schema and constraints.
4. Rental and renewal state-transition diagrams.
5. Payment verification workflow.
6. Reminder scheduling and outbox workflow.
7. API contract.
8. Security model.
9. Test plan.
10. Deployment and recovery plan.

Resolve business-critical ambiguities before implementing the corresponding feature.

After approval, implement Phase 1 first and validate its acceptance criteria before proceeding.

The final deliverable must be a secure, maintainable, extensible, and production-ready rental monitoring platform with reliable website and Telegram integration, accurate financial and rental records, and recoverable automated notification processing.