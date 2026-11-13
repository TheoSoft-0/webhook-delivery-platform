import re
from hashlib import sha256

from webhook_delivery_platform.security.api_keys import (
    generate_api_key,
    hash_api_key,
)


def test_generated_api_key_has_expected_format() -> None:
    api_key = generate_api_key()

    assert re.fullmatch(r"wdp_[A-Za-z0-9_-]{43}", api_key) is not None


def test_generated_api_keys_are_unique() -> None:
    first_key = generate_api_key()
    second_key = generate_api_key()

    assert first_key != second_key


def test_api_key_hash_matches_sha256() -> None:
    api_key = "wdp_test_secret"

    actual_hash = hash_api_key(api_key)
    expected_hash = sha256(api_key.encode("utf-8")).hexdigest()

    assert actual_hash == expected_hash


def test_api_key_hash_has_expected_length() -> None:
    api_key = generate_api_key()

    hashed_key = hash_api_key(api_key)

    assert len(hashed_key) == 64


def test_same_api_key_always_produces_same_hash() -> None:
    api_key = generate_api_key()

    first_hash = hash_api_key(api_key)
    second_hash = hash_api_key(api_key)

    assert first_hash == second_hash
