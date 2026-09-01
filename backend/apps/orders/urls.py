from rest_framework.routers import SimpleRouter

from .views import OrderViewSet

router = SimpleRouter()
router.register("", OrderViewSet, basename="order")

urlpatterns = router.urls
