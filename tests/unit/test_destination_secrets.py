from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from webhook_delivery_platform.security import destination_secrets


@pytest.fixture
def encryption_key(monkeypatch: pytest.MonkeyPatch) -> str:
    """Provide an isolated encryption key for each test."""

    key = Fernet.generate_key().decode("ascii")

    settings = SimpleNamespace(
        destination_encryption_key=SecretStr(key),
    )

    monkeypatch.setattr(
        destination_secrets,
        "get_settings",
        lambda: settings,
    )

    return key


def test_signing_secret_has_expected_format() -> None:
    secret = destination_secrets.generate_signing_secret()

    assert secret.startswith("whsec_")
    assert len(secret) > len("whsec_")


def test_generated_signing_secrets_are_unique() -> None:
    first_secret = destination_secrets.generate_signing_secret()
    second_secret = destination_secrets.generate_signing_secret()

    assert first_secret != second_secret


def test_signing_secret_can_be_encrypted_and_decrypted(
    encryption_key: str,
) -> None:
    original_secret = destination_secrets.generate_signing_secret()

    ciphertext = destination_secrets.encrypt_signing_secret(original_secret)

    decrypted_secret = destination_secrets.decrypt_signing_secret(ciphertext)

    assert decrypted_secret == original_secret


def test_ciphertext_does_not_contain_original_secret(
    encryption_key: str,
) -> None:
    original_secret = destination_secrets.generate_signing_secret()

    ciphertext = destination_secrets.encrypt_signing_secret(original_secret)

    assert original_secret not in ciphertext


def test_encrypting_same_secret_produces_different_ciphertexts(
    encryption_key: str,
) -> None:
    original_secret = destination_secrets.generate_signing_secret()

    first_ciphertext = destination_secrets.encrypt_signing_secret(original_secret)

    second_ciphertext = destination_secrets.encrypt_signing_secret(original_secret)

    assert first_ciphertext != second_ciphertext


def test_tampered_ciphertext_cannot_be_decrypted(
    encryption_key: str,
) -> None:
    original_secret = destination_secrets.generate_signing_secret()

    ciphertext = destination_secrets.encrypt_signing_secret(original_secret)

    replacement_character = "A" if ciphertext[-2] != "A" else "B"
    tampered_ciphertext = ciphertext[:-2] + replacement_character + ciphertext[-1]

    with pytest.raises(ValueError, match="cannot be decrypted"):
        destination_secrets.decrypt_signing_secret(tampered_ciphertext)


def test_ciphertext_cannot_be_decrypted_with_another_key(
    encryption_key: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_secret = destination_secrets.generate_signing_secret()

    ciphertext = destination_secrets.encrypt_signing_secret(original_secret)

    different_key = Fernet.generate_key().decode("ascii")

    different_settings = SimpleNamespace(
        destination_encryption_key=SecretStr(different_key),
    )

    monkeypatch.setattr(
        destination_secrets,
        "get_settings",
        lambda: different_settings,
    )

    with pytest.raises(ValueError, match="cannot be decrypted"):
        destination_secrets.decrypt_signing_secret(ciphertext)


def test_empty_signing_secret_cannot_be_encrypted(
    encryption_key: str,
) -> None:
    with pytest.raises(ValueError, match="cannot be empty"):
        destination_secrets.encrypt_signing_secret("")
