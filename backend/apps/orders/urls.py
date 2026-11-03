from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ManualInvoicePayView, ManualInvoicesView, OrderViewSet

router = SimpleRouter()
router.register("", OrderViewSet, basename="order")

# v1.38 «فاکتور دستی» (before the router: its detail route would read "manual-invoices" as an order id)
urlpatterns = [
    path("manual-invoices/", ManualInvoicesView.as_view(), name="manual-invoices"),
    path("manual-invoices/<int:pk>/pay/", ManualInvoicePayView.as_view(), name="manual-invoice-pay"),
] + router.urls
