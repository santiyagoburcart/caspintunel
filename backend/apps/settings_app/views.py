from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.public_cache import cached_public

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
    # cheap cached reads loaded on every page view: their own generous per-IP
    # scope instead of the global anon limit (see REST_FRAMEWORK in settings)
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"

    @extend_schema(responses=PublicSiteConfigSerializer, summary="Public branding / site config")
    def get(self, request):
        return cached_public(request, "config", lambda: Response(
            PublicSiteConfigSerializer(SiteConfig.load(), context={"request": request}).data))


class PublicActiveThemeView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"

    @extend_schema(responses=PublicThemeSerializer, summary="The active theme's palette")
    def get(self, request):
        def build():
            theme = Theme.objects.filter(is_active=True).first() or Theme.objects.first()
            if not theme:
                return Response({}, status=204)
            return Response(PublicThemeSerializer(theme).data)
        return cached_public(request, "theme", build)


class PublicPageListView(generics.ListAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"
    serializer_class = PublicPageSerializer
    queryset = Page.objects.filter(is_active=True).order_by("slug")

    def list(self, request, *args, **kwargs):
        return cached_public(request, "pages", lambda: super(PublicPageListView, self).list(request, *args, **kwargs))


class PublicPageDetailView(generics.RetrieveAPIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = PublicPageSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_read"
    lookup_field = "slug"
    queryset = Page.objects.filter(is_active=True)

    def retrieve(self, request, *args, **kwargs):
        return cached_public(request, "page", lambda: super(PublicPageDetailView, self).retrieve(request, *args, **kwargs))
