from django.urls import path

from .views import (
    BankCardListView,
    PaymentApproveView,
    PaymentPendingListView,
    PaymentRejectView,
    ReceiptUploadView,
    SmsInboundView,
    SmsPingView,
)

app_name = "payments"

urlpatterns = [
    path("cards/", BankCardListView.as_view(), name="cards"),
    path("receipt/", ReceiptUploadView.as_view(), name="receipt"),
    path("pending/", PaymentPendingListView.as_view(), name="pending"),
    path("<int:pk>/approve/", PaymentApproveView.as_view(), name="approve"),
    path("<int:pk>/reject/", PaymentRejectView.as_view(), name="reject"),
    # Android SMS app
    path("sms/inbound/", SmsInboundView.as_view(), name="sms-inbound"),
    path("sms/ping/", SmsPingView.as_view(), name="sms-ping"),
]
