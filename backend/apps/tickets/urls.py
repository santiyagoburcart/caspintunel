from django.urls import path

from . import views

urlpatterns = [
    path("topics/", views.TopicsView.as_view(), name="tickets-topics"),
    path("attachments/<int:pk>/", views.AttachmentFileView.as_view(), name="tickets-attachment"),
    path("", views.TicketListView.as_view(), name="tickets-list"),
    path("<int:pk>/", views.TicketDetailView.as_view(), name="tickets-detail"),
    path("<int:pk>/reply/", views.TicketReplyView.as_view(), name="tickets-reply"),
    path("<int:pk>/close/", views.TicketCloseView.as_view(), name="tickets-close"),
    path("<int:pk>/reopen/", views.TicketReopenView.as_view(), name="tickets-reopen"),
]
