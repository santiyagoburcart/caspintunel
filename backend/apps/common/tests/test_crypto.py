from cryptography.fernet import Fernet
from django.test import override_settings

from apps.common.crypto import decrypt, encrypt

KEY = Fernet.generate_key().decode()


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_encrypt_roundtrip():
    secret = "s3cr3t-panel-password"
    enc = encrypt(secret)
    assert enc != secret
    assert enc.startswith("enc:v1:")
    assert decrypt(enc) == secret


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_encrypt_handles_empty_and_none():
    assert encrypt("") == ""
    assert encrypt(None) is None
    assert decrypt("") == ""
    assert decrypt(None) is None


@override_settings(FIELD_ENCRYPTION_KEY=KEY)
def test_decrypt_passes_through_legacy_plaintext():
    assert decrypt("not-encrypted-yet") == "not-encrypted-yet"
