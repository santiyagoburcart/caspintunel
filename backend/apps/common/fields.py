"""Model fields that transparently encrypt their value at rest."""
from __future__ import annotations

from django.db import models

from .crypto import decrypt, encrypt


class EncryptedTextField(models.TextField):
    """
    Stores an encrypted blob in a TEXT column; exposes plaintext in Python.

    Not searchable / filterable by value (by design). Use for panel passwords,
    bot tokens, API tokens, etc.
    """

    description = "Text field encrypted at rest (Fernet)"

    def from_db_value(self, value, expression, connection):
        return decrypt(value)

    def to_python(self, value):
        if value is None:
            return value
        # value may already be plaintext (forms, freshly set attribute)
        return decrypt(value) if isinstance(value, str) and value.startswith("enc:v1:") else value

    def get_prep_value(self, value):
        if value is None:
            return value
        return encrypt(str(value))


class EncryptedCharField(EncryptedTextField):
    """Same as EncryptedTextField but presented as a shorter form widget."""

    def formfield(self, **kwargs):
        kwargs.setdefault("max_length", self.max_length)
        return super().formfield(**kwargs)
