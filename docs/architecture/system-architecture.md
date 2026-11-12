# System Architecture

Status: Initial design proposal

## 1. Purpose

This document describes the planned application components and their responsibilities.

It also defines the main processing workflows, API operations, and acceptance criteria.

The application runs locally using Docker Compose.

## 2. Application Components

### FastAPI Application

Responsibilities:

- Expose the REST API.
- Authenticate incoming API requests.
- Validate incoming data.
- Manage destinations and subscriptions.
- Accept incoming events.
- Create event, delivery, and outbox records.
- Expose event and delivery history.

The API must not wait for webhook delivery to finish.

### PostgreSQL

Responsibilities:

- Store applications and API keys.
- Store registered destinations and subscriptions.
- Store incoming events.
- Store delivery records and attempt history.
- Store pending outbox messages.

PostgreSQL is the authoritative source of application data.

### Outbox Dispatcher

Responsibilities:

- Find pending outbox messages.
- Publish delivery jobs to Redis.
- Record successful queue publication.
- Retry publication when necessary.

The dispatcher operates independently of API requests.

### Redis

Responsibilities:

- Act as the Celery message broker.
- Hold jobs waiting for background workers.

Redis does not replace PostgreSQL as the authoritative data store.

### Celery Workers

Responsibilities:

- Receive delivery jobs.
- Claim eligible deliveries.
- Send HTTP POST requests.
- Record delivery attempts.
- Determine whether failures should be retried.
- Schedule subsequent attempts.

Workers must handle duplicate jobs safely.

### HTTPX

HTTPX performs outgoing HTTP requests to registered destinations.

The request timeout and network error handling must be configurable.

### Local Webhook Receiver

A local receiver will demonstrate successful webhook delivery.

It will also verify HMAC signatures during development and testing.

## 3. Component Communication

The main communication paths are:

1. External applications communicate with FastAPI using HTTP.
2. FastAPI communicates with PostgreSQL.
3. The Outbox Dispatcher reads pending records from PostgreSQL.
4. The Outbox Dispatcher publishes jobs through Redis.
5. Celery Workers receive jobs through Redis.
6. Workers communicate with PostgreSQL and external destinations.

## 4. Event Processing Workflow

When an external application submits an event:

1. FastAPI authenticates the API key.
2. FastAPI validates the event type and payload.
3. FastAPI checks the Idempotency-Key.
4. FastAPI identifies enabled destinations subscribed to that event type.
5. One database transaction stores the Event.
6. The same transaction creates one Delivery per matching Destination.
7. The transaction creates one initial OutboxMessage per Delivery.
8. PostgreSQL commits the transaction.
9. FastAPI returns HTTP 202 Accepted.

An event without matching subscriptions is still stored.

Such an event produces zero Delivery records.

## 5. Background Delivery Workflow

The Outbox Dispatcher continuously checks PostgreSQL.

It selects pending messages that are ready for publication.

It publishes a Celery job containing the OutboxMessage ID.

After successful publication, it marks the message as published.

A crash after publication but before recording that publication can produce duplicate jobs.

Workers must therefore make job processing idempotent.

An idempotent operation prevents duplicate execution from creating duplicate effects.

Each DeliveryAttempt references its originating OutboxMessage.

The database must prevent multiple attempts from being created for the same OutboxMessage.

The worker then:

1. Claims the Delivery.
2. Creates a DeliveryAttempt.
3. Sends the HTTP POST request.
4. Records the HTTP response or network error.
5. Updates the Delivery status.
6. Schedules another attempt when appropriate.

## 6. Delivery Statuses

A Delivery can have these statuses:

| Status             | Meaning                                    |
| ------------------ | ------------------------------------------ |
| pending            | Created and awaiting initial processing.   |
| scheduled          | Waiting for processing or another attempt. |
| processing         | Currently being processed by a worker.     |
| succeeded          | A successful HTTP response was received.   |
| permanently_failed | No further automatic attempts will occur.  |

The Delivery status must reflect its actual processing state.

A DeliveryAttempt records the result of one individual attempt.

## 7. Retry Policy

The initial configuration uses a maximum of five automatic attempts per retry cycle.

Temporary failures include:

- Connection failures.
- Request timeouts.
- HTTP 408.
- HTTP 425.
- HTTP 429.
- HTTP 5xx responses.

Other HTTP 3xx and 4xx responses are treated as permanent failures.

A successful HTTP 2xx response completes the Delivery.

Automatic retries use exponential backoff.

The initial delay is two seconds.

Subsequent delays double until reaching a maximum of five minutes.

A failed Delivery becomes permanently_failed when automatic retries are exhausted.

Manual retry starts a new retry cycle.

Previous DeliveryAttempts must remain available for inspection.

The DeliveryAttempt records identify their retry cycle.

## 8. Transactional Outbox

The platform uses the transactional outbox pattern.

Creating a Delivery and its initial OutboxMessage happens within one PostgreSQL transaction.

This prevents a Delivery from being stored without its corresponding scheduling instruction.

Each subsequent retry creates another OutboxMessage.

One Delivery can therefore have multiple OutboxMessages.

Each OutboxMessage can produce at most one DeliveryAttempt.

The dispatcher may publish the same message more than once.

Worker processing must remain safe when that happens.

## 9. API Contract

All business API endpoints use the `/v1` prefix.

Operational health endpoints are intentionally unversioned.
They use `/health/live` and `/health/ready`.

Authenticated endpoints require:

`Authorization: Bearer <api_key>`

The API key identifies the owning Application.

Applications must only access their own records.

### Application provisioning

Applications and their initial API keys are created through a local CLI command.

The raw API key is displayed only once.

The database stores its cryptographic hash.

### Destination operations

| Method | Endpoint                                           | Purpose                          |
| ------ | -------------------------------------------------- | -------------------------------- |
| POST   | `/v1/destinations`                                 | Register a destination.          |
| GET    | `/v1/destinations`                                 | List registered destinations.    |
| GET    | `/v1/destinations/{id}`                            | Inspect a destination.           |
| PATCH  | `/v1/destinations/{id}`                            | Enable or disable a destination. |
| PUT    | `/v1/destinations/{id}/subscriptions/{event_type}` | Add a subscription.              |
| DELETE | `/v1/destinations/{id}/subscriptions/{event_type}` | Remove a subscription.           |

Creating a destination generates its signing secret.

The raw signing secret is returned once.

The database stores the encrypted signing secret.

### Event operations

| Method | Endpoint                     | Purpose                 |
| ------ | ---------------------------- | ----------------------- |
| POST   | `/v1/events`                 | Submit an event.        |
| GET    | `/v1/events/{id}`            | Inspect an event.       |
| GET    | `/v1/events/{id}/deliveries` | Inspect its deliveries. |

Event submission requires an `Idempotency-Key` header.

Repeated requests with the same key and identical content return the original event.

Reusing a key with different content returns HTTP 409 Conflict.

### Delivery operations

| Method | Endpoint                       | Purpose                              |
| ------ | ------------------------------ | ------------------------------------ |
| GET    | `/v1/deliveries/{id}`          | Inspect delivery status.             |
| GET    | `/v1/deliveries/{id}/attempts` | Inspect delivery attempts.           |
| POST   | `/v1/deliveries/{id}/retry`    | Manually retry an eligible delivery. |

The API must check application ownership for every requested resource.

### Health operations

| Method | Endpoint        | Purpose                                                |
| ------ | --------------- | ------------------------------------------------------ |
| GET    | `/health/live`  | Check whether the API process is running.              |
| GET    | `/health/ready` | Check whether required API dependencies are available. |

## 10. Webhook Signatures

Outgoing requests use HMAC-SHA256 signatures.

The signature is calculated using the destination signing secret.

The signature includes the request timestamp and raw request body.

Outgoing requests include:

- `X-Webhook-Event-Id`
- `X-Webhook-Event-Type`
- `X-Webhook-Signature`

Signing secrets must be encrypted in PostgreSQL.

The encryption key must come from local environment configuration.

Secrets must never be committed to Git.

## 11. SSRF Protection

Destination URLs must be validated before outgoing requests.

Only HTTP and HTTPS schemes are permitted.

URLs containing embedded usernames or passwords are rejected.

Private, loopback, link-local, multicast, and unspecified network addresses are blocked.

DNS resolution must be checked when establishing outbound connections.

This prevents DNS changes from bypassing destination validation.

HTTP redirects are disabled initially.

Local destination exceptions must require an explicit development-only setting.

Private destinations must remain blocked outside development.

## 12. Acceptance Criteria

The application is accepted when:

1. Docker Compose starts all required local services.
2. An Application and API key can be created through the CLI.
3. An authenticated client can register a Destination.
4. A Destination can subscribe to event types.
5. An authenticated client can submit an Event.
6. Events and their scheduling records are committed atomically.
7. Only matching enabled destinations receive deliveries.
8. Duplicate idempotency keys cannot create duplicate events.
9. Background workers deliver events independently of API requests.
10. Every delivery attempt is recorded.
11. Outgoing webhook signatures can be verified.
12. Temporary failures trigger automatic retries.
13. Permanent failures stop automatic retries.
14. Manual retries preserve previous attempt history.
15. Duplicate background jobs cannot create duplicate attempts.
16. SSRF protection is covered by automated tests.
17. All important behaviour has automated tests.
18. GitHub Actions runs the automated test suite successfully.
19. The public README explains installation and usage.
20. The project runs locally without paid services.

## 13. Deferred Implementation Details

These details will be finalised during implementation:

- Exact database column types and indexes.
- Exact Celery configuration.
- Exact worker concurrency settings.
- Recovery of workers interrupted during delivery.
- Logging structure and operational metrics.
- API pagination.
- Exact environment variable names.

Changes to this design must be documented when implementation reveals a technical requirement.
