"""Customer JWT authentication with password-based session revocation.

SIMPLE_JWT["CHECK_REVOKE_TOKEN"] stamps every new token with a hash of the
user's password hash, so changing / invalidating the password (e.g. on a
Telegram ↔ site account merge) kills every outstanding access token.

simplejwt's stock check rejects tokens that lack the claim, which would log
out every customer the moment this was deployed. This class accepts
claim-less tokens (issued before the switch; they expire within the access
lifetime) — except for accounts whose password is unusable, i.e. exactly the
accounts a merge just locked.
"""
from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from rest_framework_simplejwt.authentication import JWTAuthentication as _Base
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password


def token_matches_password(validated_token, user) -> bool:
    claim = validated_token.get(api_settings.REVOKE_TOKEN_CLAIM)
    if claim is None:
        return user.has_usable_password()
    return claim == get_md5_hash_password(user.password)


class JWTAuthentication(_Base):
    def get_user(self, validated_token):
        try:
            user_id = validated_token[api_settings.USER_ID_CLAIM]
        except KeyError as e:
            raise InvalidToken(_("Token contained no recognizable user identification")) from e
        try:
            user = self.user_model.objects.get(**{api_settings.USER_ID_FIELD: user_id})
        except self.user_model.DoesNotExist as e:
            raise AuthenticationFailed(_("User not found"), code="user_not_found") from e
        if api_settings.CHECK_USER_IS_ACTIVE and not user.is_active:
            raise AuthenticationFailed(_("User is inactive"), code="user_inactive")
        if not token_matches_password(validated_token, user):
            raise AuthenticationFailed(_("The user's password has been changed."), code="password_changed")
        return user
