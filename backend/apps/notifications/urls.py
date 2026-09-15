from rest_framework.routers import SimpleRouter

from .views import NotificationDeliveryViewSet

router = SimpleRouter()
router.register("", NotificationDeliveryViewSet, basename="notification")

urlpatterns = router.urls
