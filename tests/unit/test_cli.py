from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy.exc import SQLAlchemyError

from webhook_delivery_platform import cli
from webhook_delivery_platform.services.application_provisioning import (
    ProvisionedApplication,
)


def test_cli_displays_api_key_once_after_success(
    monkeypatch,
    capsys,
) -> None:
    provisioned = ProvisionedApplication(
        application_id=uuid4(),
        api_key_id=uuid4(),
        raw_api_key="wdp_test_secret",
    )

    monkeypatch.setattr(
        cli,
        "SessionFactory",
        SimpleNamespace(begin=lambda: nullcontext(object())),
    )

    def fake_provision(session, name):
        assert name == "CLI Test Application"
        return provisioned

    monkeypatch.setattr(cli, "provision_application", fake_provision)

    exit_code = cli.main(
        [
            "create-application",
            "--name",
            "CLI Test Application",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.count(provisioned.raw_api_key) == 1
    assert str(provisioned.application_id) in captured.out
    assert captured.err == ""


def test_cli_does_not_display_api_key_when_commit_fails(
    monkeypatch,
    capsys,
) -> None:
    provisioned = ProvisionedApplication(
        application_id=uuid4(),
        api_key_id=uuid4(),
        raw_api_key="wdp_test_secret",
    )

    @contextmanager
    def failing_transaction():
        yield object()
        raise SQLAlchemyError("Simulated commit failure")

    monkeypatch.setattr(
        cli,
        "SessionFactory",
        SimpleNamespace(begin=failing_transaction),
    )

    monkeypatch.setattr(
        cli,
        "provision_application",
        lambda session, name: provisioned,
    )

    exit_code = cli.main(
        [
            "create-application",
            "--name",
            "CLI Test Application",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == ""
    assert provisioned.raw_api_key not in captured.err
    assert "Database error" in captured.err


def test_cli_reports_invalid_application_name(
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.setattr(
        cli,
        "SessionFactory",
        SimpleNamespace(begin=lambda: nullcontext(object())),
    )

    def reject_application(session, name):
        raise ValueError("Application name cannot be empty.")

    monkeypatch.setattr(
        cli,
        "provision_application",
        reject_application,
    )

    exit_code = cli.main(
        [
            "create-application",
            "--name",
            "   ",
        ]
    )

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Application name cannot be empty." in captured.err
    assert captured.out == ""
