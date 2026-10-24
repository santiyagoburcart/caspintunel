from django.urls import path

from .views import (
    BankCardListView,
    PaymentApproveView,
    PaymentPendingListView,
    PaymentRejectView,
    ReceiptFileView,
    ReceiptUploadView,
    SmsInboundBatchView,
    SmsInboundView,
    SmsPingView,
    SmsSourcesView,
)

app_name = "payments"

urlpatterns = [
    path("cards/", BankCardListView.as_view(), name="cards"),
    path("receipt/", ReceiptUploadView.as_view(), name="receipt"),
    path("pending/", PaymentPendingListView.as_view(), name="pending"),
    path("<int:pk>/receipt/", ReceiptFileView.as_view(), name="receipt-file"),
    path("<int:pk>/approve/", PaymentApproveView.as_view(), name="approve"),
    path("<int:pk>/reject/", PaymentRejectView.as_view(), name="reject"),
    # Android SMS app
    path("sms/inbound/", SmsInboundView.as_view(), name="sms-inbound"),
    path("sms/inbound-batch/", SmsInboundBatchView.as_view(), name="sms-inbound-batch"),
    path("sms/ping/", SmsPingView.as_view(), name="sms-ping"),
    path("sms/sources/", SmsSourcesView.as_view(), name="sms-sources"),
]
