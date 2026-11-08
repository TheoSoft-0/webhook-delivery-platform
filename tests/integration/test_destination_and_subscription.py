from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import (
    Application,
    Destination,
    Subscription,
)


def create_application(db_session: Session) -> Application:
    application = Application(name="Integration Test Application")
    db_session.add(application)
    db_session.flush()
    return application


def create_destination(
    db_session: Session,
    application: Application,
) -> Destination:
    destination = Destination(
        application=application,
        url="https://receiver.example/webhook",
        signing_secret_ciphertext="test-ciphertext",
    )
    db_session.add(destination)
    db_session.flush()
    return destination


def test_destination_belongs_to_application_and_is_enabled_by_default(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    destination = create_destination(db_session, application)

    assert destination.application_id == application.id
    assert destination.application.id == application.id
    assert destination.is_enabled is True


def test_subscription_belongs_to_destination(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    destination = create_destination(db_session, application)

    subscription = Subscription(
        destination=destination,
        event_type="order.created",
    )

    db_session.add(subscription)
    db_session.flush()

    assert subscription.destination_id == destination.id
    assert subscription.destination.id == destination.id
    assert subscription.event_type == "order.created"


def test_subscription_rejects_nonexistent_destination(
    db_session: Session,
) -> None:
    subscription = Subscription(
        destination_id=uuid4(),
        event_type="order.created",
    )

    db_session.add(subscription)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_subscription_is_rejected(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    destination = create_destination(db_session, application)

    first_subscription = Subscription(
        destination=destination,
        event_type="order.created",
    )

    db_session.add(first_subscription)
    db_session.flush()

    second_subscription = Subscription(
        destination=destination,
        event_type="order.created",
    )

    db_session.add(second_subscription)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_destination_rejects_blank_url(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    destination = Destination(
        application=application,
        url="   ",
        signing_secret_ciphertext="test-ciphertext",
    )

    db_session.add(destination)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_subscription_rejects_blank_event_type(
    db_session: Session,
) -> None:
    application = create_application(db_session)
    destination = create_destination(db_session, application)

    subscription = Subscription(
        destination=destination,
        event_type="   ",
    )

    db_session.add(subscription)

    with pytest.raises(IntegrityError):
        db_session.flush()


def test_different_destinations_can_subscribe_to_same_event_type(
    db_session: Session,
) -> None:
    application = create_application(db_session)

    first_destination = create_destination(db_session, application)
    second_destination = create_destination(db_session, application)

    first_subscription = Subscription(
        destination=first_destination,
        event_type="order.created",
    )

    second_subscription = Subscription(
        destination=second_destination,
        event_type="order.created",
    )

    db_session.add_all([first_subscription, second_subscription])
    db_session.flush()

    assert first_subscription.destination_id != second_subscription.destination_id
    assert first_subscription.event_type == second_subscription.event_type
