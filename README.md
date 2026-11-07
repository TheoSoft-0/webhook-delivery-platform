# Reliable Webhook Delivery Platform

A locally deployable webhook delivery platform built with Python.

The project focuses on reliable event processing, background delivery,
failure handling, and secure communication with registered destinations.

**Project status: Under active development.**

The architecture is documented. Application functionality is not yet implemented.

## Project Objectives

This project has two objectives:

1. Demonstrate practical backend and software engineering competencies.
2. Develop deeper understanding of production-oriented software engineering.

The implementation emphasizes reliability, security, maintainability,
automated testing, and clear architectural responsibilities.

## Planned Functionality

- Application authentication using API keys.
- Webhook destination registration and management.
- Event submission through a REST API.
- Subscription-based event routing.
- Background webhook delivery.
- HMAC-SHA256 request signatures.
- Delivery attempt tracking and history.
- Automatic retries using exponential backoff.
- Transactional outbox pattern.
- Idempotency protection.
- Server-side request forgery protection.

These features are planned. They are not yet implemented.

## Planned Technology Stack

| Technology     | Responsibility                           |
| -------------- | ---------------------------------------- |
| Python 3.13    | Application language                     |
| FastAPI        | REST API                                 |
| PostgreSQL     | Persistent data storage                  |
| SQLAlchemy     | Database operations                      |
| Alembic        | Database migrations                      |
| Redis          | Background job message broker            |
| Celery         | Background workers                       |
| HTTPX          | Outgoing HTTP requests                   |
| Docker Compose | Local infrastructure                     |
| pytest         | Automated testing                        |
| uv             | Python project and dependency management |
| GitHub Actions | Continuous integration                   |

## Architecture Documentation

- [Database Relationships](docs/architecture/database-relationships.md)
- [System Architecture](docs/architecture/system-architecture.md)

## Local Development

Local development will use Docker Compose.

Setup and execution instructions will be added as implementation progresses.

No paid cloud services or external paid APIs are required.

## Reliability Goals

The platform will provide at-least-once delivery semantics.

Exactly-once HTTP delivery is not guaranteed.

Receiving applications must be able to identify duplicate events.

## Project Status

The project is currently in its initial development stage.

The architecture and requirements have been documented.

Implementation, automated tests, and deployment configuration remain outstanding.

## License

License not yet selected.
