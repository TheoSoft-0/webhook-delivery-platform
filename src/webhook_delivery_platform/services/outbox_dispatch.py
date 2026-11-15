from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import OutboxMessage
from webhook_delivery_platform.services.message_publisher import (
    MessagePublisher,
    MessagePublishError,
)


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Results from one dispatcher execution."""

    published_count: int
    failed_count: int


def dispatch_outbox_messages(
    session: Session,
    publisher: MessagePublisher,
    *,
    batch_size: int,
    recovery_interval: timedelta,
    publication_retry_interval: timedelta,
) -> DispatchResult:
    """Publish eligible outbox messages.

    Eligible messages are:
    - Pending messages whose available_at timestamp has arrived.
    - Published messages whose publication is stale and whose worker
      lease is absent or expired.

    The selected database records remain locked during publication.

    Expected publication failures are recorded in last_error.
    Unexpected exceptions propagate to the caller.

    The caller is responsible for committing or rolling back the transaction.

    Messages with a future next_publish_at timestamp are skipped.
    Failed publications become eligible again after the retry interval.
    """

    if batch_size < 1:
        raise ValueError("batch_size must be greater than zero.")

    if recovery_interval <= timedelta(0):
        raise ValueError("recovery_interval must be greater than zero.")
    if publication_retry_interval <= timedelta(0):
        raise ValueError("publication_retry_interval must be greater than zero.")
    database_now = session.scalar(select(func.clock_timestamp()))

    if database_now is None:
        raise RuntimeError("PostgreSQL did not return its current timestamp.")

    stale_before = database_now - recovery_interval
    publication_retry_due = or_(
        OutboxMessage.next_publish_at.is_(None),
        OutboxMessage.next_publish_at <= database_now,
    )
    eligible_messages = or_(
        and_(
            OutboxMessage.status == "pending",
            OutboxMessage.available_at <= database_now,
            publication_retry_due,
        ),
        and_(
            OutboxMessage.status == "published",
            OutboxMessage.published_at <= stale_before,
            publication_retry_due,
            or_(
                OutboxMessage.lease_token.is_(None),
                OutboxMessage.lease_expires_at <= database_now,
            ),
        ),
    )

    statement = (
        select(OutboxMessage)
        .where(eligible_messages)
        .order_by(
            OutboxMessage.available_at,
            OutboxMessage.created_at,
            OutboxMessage.id,
        )
        .limit(batch_size)
        .with_for_update(skip_locked=True)
    )

    messages = session.scalars(statement).all()

    published_count = 0
    failed_count = 0

    for message in messages:
        try:
            publisher.publish(message.id)

        except MessagePublishError:
            # Do not store raw broker errors.
            # They could contain connection details or credentials.
            failed_at = session.scalar(select(func.clock_timestamp()))

            if failed_at is None:
                raise RuntimeError("PostgreSQL did not return its current timestamp.")

            message.next_publish_at = failed_at + publication_retry_interval
            message.last_error = "Message broker publication failed."
            failed_count += 1
            continue

        published_at = session.scalar(select(func.clock_timestamp()))

        if published_at is None:
            raise RuntimeError("PostgreSQL did not return the publication timestamp.")

        message.status = "published"
        message.published_at = published_at
        message.last_error = None
        message.next_publish_at = None
        published_count += 1

    session.flush()

    return DispatchResult(
        published_count=published_count,
        failed_count=failed_count,
    )
