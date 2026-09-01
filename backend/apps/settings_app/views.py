from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Page, SiteConfig, Theme
from .serializers import PublicPageSerializer, PublicSiteConfigSerializer, PublicThemeSerializer


class PublicSiteConfigView(APIView):
    # No auth at all: both frontends' shared `api` client always attaches a
    # bearer token when one is present (admin staff token, user token) — even
    # on public calls like this one. SimpleJWT's JWTAuthentication doesn't
    # recognize the staff token shape and raises 401 despite AllowAny, which
    # trips the axios refresh-token interceptor on every page load. Truly
    # public endpoints must skip authentication entirely, not just permission.
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicSiteConfigSerializer, summary="Public branding / site config")
    def get(self, request):
        return Response(PublicSiteConfigSerializer(SiteConfig.load(), context={"request": request}).data)


class PublicActiveThemeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicThemeSerializer, summary="The active theme's palette")
    def get(self, request):
        theme = Theme.objects.filter(is_active=True).first() or Theme.objects.first()
        if not theme:
            return Response({}, status=204)
        return Response(PublicThemeSerializer(theme).data)


class PublicPageListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicPageSerializer
    queryset = Page.objects.filter(is_active=True).order_by("slug")


class PublicPageDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicPageSerializer
    lookup_field = "slug"
    queryset = Page.objects.filter(is_active=True)
