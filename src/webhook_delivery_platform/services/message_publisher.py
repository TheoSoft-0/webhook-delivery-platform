from typing import Protocol
from uuid import UUID


class MessagePublishError(Exception):
    """Raised when a message cannot be published to the broker."""


class MessagePublisher(Protocol):
    """Interface for publishing an OutboxMessage ID."""

    def publish(self, message_id: UUID) -> None:
        """Submit a message to the broker.

        Return when the publisher's send operation succeeds.

        A successful return does not mean a worker has received or processed
        the job.
        """
        ...
