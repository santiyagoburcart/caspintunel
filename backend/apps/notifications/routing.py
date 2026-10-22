from django.urls import re_path

from apps.tickets.consumers import StaffTicketsConsumer

from .consumers import NotificationConsumer, StaffPaymentsConsumer

websocket_urlpatterns = [
    re_path(r"^ws/notifications/$", NotificationConsumer.as_asgi()),
    re_path(r"^ws/admin/payments/$", StaffPaymentsConsumer.as_asgi()),
    re_path(r"^ws/admin/tickets/$", StaffTicketsConsumer.as_asgi()),
]
