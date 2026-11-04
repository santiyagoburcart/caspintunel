"""Customer JWTs carry the tenant (`tid`, docs/multi-tenant.md §3). The refresh → access copy keeps the claim. A token
used on another tenant's host is refused (apps/accounts/authentication.py); tokens issued before v1.41 have no `tid`
and are accepted (the user lookup is tenant-scoped anyway)."""
from rest_framework_simplejwt.tokens import RefreshToken

TID_CLAIM = "tid"


def customer_refresh(user) -> RefreshToken:
    r = RefreshToken.for_user(user)
    if getattr(user, "tenant_id", None):
        r[TID_CLAIM] = user.tenant_id
    return r
