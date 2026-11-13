import pytest
from sqlalchemy.orm import Session

from webhook_delivery_platform.models import ApiKey, Application
from webhook_delivery_platform.security.api_keys import hash_api_key
from webhook_delivery_platform.services.application_provisioning import (
    provision_application,
)


def test_provision_application_creates_application_and_api_key(
    db_session: Session,
) -> None:
    provisioned = provision_application(
        db_session,
        "  Provisioning Test Application  ",
    )

    application = db_session.get(
        Application,
        provisioned.application_id,
    )

    api_key = db_session.get(
        ApiKey,
        provisioned.api_key_id,
    )

    assert application is not None
    assert application.name == "Provisioning Test Application"

    assert api_key is not None
    assert api_key.application_id == application.id

    assert api_key.key_hash == hash_api_key(provisioned.raw_api_key)
    assert api_key.key_hash != provisioned.raw_api_key

    assert api_key.revoked_at is None
    assert provisioned.raw_api_key not in repr(provisioned)


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "x" * 121,
    ],
)
def test_provision_application_rejects_invalid_names(
    db_session: Session,
    name: str,
) -> None:
    with pytest.raises(ValueError):
        provision_application(db_session, name)
