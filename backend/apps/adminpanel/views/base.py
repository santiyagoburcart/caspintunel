from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from apps.accounts.authentication import JWTAuthentication

from ..permissions import RefuseManagerToken, StaffJWTAuthentication, StaffPermission

# RefuseManagerToken last: the first class still answers 401 (WWW-Authenticate) for anonymous requests
_AUTH = [StaffJWTAuthentication, JWTAuthentication, SessionAuthentication, RefuseManagerToken]


class AdminAPIView(APIView):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]


class AdminViewSet(viewsets.ModelViewSet):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
