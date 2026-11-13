import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.exc import SQLAlchemyError

from webhook_delivery_platform.database import SessionFactory
from webhook_delivery_platform.services.application_provisioning import (
    provision_application,
)


def create_application(name: str) -> int:
    """Create an application and display its API key once."""

    try:
        with SessionFactory.begin() as session:
            provisioned = provision_application(session, name)

    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    except SQLAlchemyError:
        print(
            "Database error. The application was not created.",
            file=sys.stderr,
        )
        return 1

    print(f"Application ID: {provisioned.application_id}")
    print(f"API key ID: {provisioned.api_key_id}")
    print(f"API key (shown once): {provisioned.raw_api_key}")

    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Administrative commands for the webhook platform."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    create_parser = subparsers.add_parser(
        "create-application",
        help="Create an application and its first API key.",
    )

    create_parser.add_argument(
        "--name",
        required=True,
        help="Name of the application.",
    )

    arguments = parser.parse_args(argv)

    if arguments.command == "create-application":
        return create_application(arguments.name)

    return 1
