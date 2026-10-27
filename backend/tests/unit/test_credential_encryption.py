from app.core.encryption import decrypt_credential, encrypt_credential


def test_credential_round_trip_does_not_store_plaintext() -> None:
    plaintext = "customer.account@example.com"

    encrypted = encrypt_credential(plaintext)

    assert encrypted is not None
    assert plaintext not in encrypted
    assert decrypt_credential(encrypted) == plaintext


def test_empty_optional_credentials_are_stored_as_null() -> None:
    assert encrypt_credential(None) is None
    assert encrypt_credential("   ") is None
    assert decrypt_credential(None) is None
