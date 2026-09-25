from rest_framework import viewsets
from rest_framework.authentication import SessionAuthentication
from rest_framework.views import APIView

from apps.accounts.authentication import JWTAuthentication

from ..permissions import StaffJWTAuthentication, StaffPermission

_AUTH = [StaffJWTAuthentication, JWTAuthentication, SessionAuthentication]


class AdminAPIView(APIView):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]


class AdminViewSet(viewsets.ModelViewSet):
    authentication_classes = _AUTH
    permission_classes = [StaffPermission]
