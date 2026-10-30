"""Login / logout endpoints start from a clean slate (v1.30.2).

- `NO_AUTH`: an auth endpoint never runs an authenticator, so whatever the browser
  still sends (an old, expired or other-app `Authorization` header, a Django session
  cookie) can't turn a correct login into a 401 / CSRF 403.
- `fresh_auth_response`: tokens are never cached, and the old root cookies
  (`sessionid` / `csrftoken` on Path=/, from versions before the Django-admin cookies
  moved to /admin/) are expired.
"""
from django.conf import settings

NO_AUTH: list = []


def fresh_auth_response(response):
    response["Cache-Control"] = "no-store"
    for name in getattr(settings, "LEGACY_ROOT_COOKIES", ()):
        response.delete_cookie(name, path="/", samesite="Lax")
    return response


class FreshAuthMixin:
    """For APIView subclasses: no authenticators + clean response."""

    authentication_classes = NO_AUTH

    def finalize_response(self, request, response, *args, **kwargs):
        return fresh_auth_response(super().finalize_response(request, response, *args, **kwargs))
