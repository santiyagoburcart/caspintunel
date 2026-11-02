from rest_framework.routers import SimpleRouter

from django.urls import path

from .views import CustomerPushView, NotificationDeliveryViewSet

router = SimpleRouter()
router.register("", NotificationDeliveryViewSet, basename="notification")

urlpatterns = [
    path("push/", CustomerPushView.as_view(), name="notifications-push"),
    path("push/<str:action>/", CustomerPushView.as_view(), name="notifications-push-action"),
] + router.urls
