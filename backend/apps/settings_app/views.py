from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Page, SiteConfig, Theme
from .serializers import PublicPageSerializer, PublicSiteConfigSerializer, PublicThemeSerializer


class PublicSiteConfigView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicSiteConfigSerializer, summary="Public branding / site config")
    def get(self, request):
        return Response(PublicSiteConfigSerializer(SiteConfig.load(), context={"request": request}).data)


class PublicActiveThemeView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=PublicThemeSerializer, summary="The active theme's palette")
    def get(self, request):
        theme = Theme.objects.filter(is_active=True).first() or Theme.objects.first()
        if not theme:
            return Response({}, status=204)
        return Response(PublicThemeSerializer(theme).data)


class PublicPageListView(generics.ListAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicPageSerializer
    queryset = Page.objects.filter(is_active=True).order_by("slug")


class PublicPageDetailView(generics.RetrieveAPIView):
    permission_classes = [AllowAny]
    serializer_class = PublicPageSerializer
    lookup_field = "slug"
    queryset = Page.objects.filter(is_active=True)
