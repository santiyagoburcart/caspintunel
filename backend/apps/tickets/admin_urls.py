from django.urls import path

from . import admin_views as v

urlpatterns = [
    path("", v.InboxView.as_view(), name="admin-tickets"),
    path("badge/", v.BadgeView.as_view(), name="admin-tickets-badge"),
    path("topics/", v.TopicsView.as_view(), name="admin-tickets-topics"),
    path("topics/<int:pk>/", v.TopicDetailView.as_view(), name="admin-tickets-topic"),
    path("settings/", v.SettingsView.as_view(), name="admin-tickets-settings"),
    path("staff-scopes/", v.StaffScopesView.as_view(), name="admin-tickets-scopes"),
    path("staff-scopes/<int:pk>/", v.StaffScopeDetailView.as_view(), name="admin-tickets-scope"),
    path("telegram-link/", v.TelegramLinkView.as_view(), name="admin-tickets-telegram-link"),
    path("<int:pk>/", v.TicketDetailView.as_view(), name="admin-ticket"),
    path("<int:pk>/reply/", v.ReplyView.as_view(), name="admin-ticket-reply"),
    path("<int:pk>/assign/", v.AssignView.as_view(), name="admin-ticket-assign"),
    path("<int:pk>/assignable/", v.AssignableStaffView.as_view(), name="admin-ticket-assignable"),
    path("<int:pk>/status/", v.StatusView.as_view(), name="admin-ticket-status"),
    path("<int:pk>/priority/", v.PriorityView.as_view(), name="admin-ticket-priority"),
]
