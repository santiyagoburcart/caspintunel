from django.urls import path

from . import views as v

urlpatterns = [
    path("customers/<int:pk>/", v.CustomerView.as_view(), name="crm-customer"),
    path("customers/<int:pk>/timeline/", v.TimelineView.as_view(), name="crm-timeline"),
    path("customers/<int:pk>/notes/", v.NotesView.as_view(), name="crm-notes"),
    path("customers/<int:pk>/cases/", v.CustomerCaseView.as_view(), name="crm-customer-cases"),
    path("customers/<int:pk>/message/", v.CustomerMessageView.as_view(), name="crm-customer-message"),
    path("customers/<int:pk>/templates/<int:tpl>/preview/", v.TemplatePreviewView.as_view(), name="crm-template-preview"),
    path("cases/", v.CasesView.as_view(), name="crm-cases"),
    path("cases/<int:pk>/", v.CaseView.as_view(), name="crm-case"),
    path("cases/<int:pk>/close/", v.CaseCloseView.as_view(), name="crm-case-close"),
    path("cases/<int:pk>/message/", v.CaseMessageView.as_view(), name="crm-case-message"),
    path("cases/<int:pk>/ticket/", v.CaseTicketView.as_view(), name="crm-case-ticket"),
    path("leads/", v.LeadsView.as_view(), name="crm-leads"),
    path("staff/", v.StaffListView.as_view(), name="crm-staff"),
    path("reports/", v.ReportsView.as_view(), name="crm-reports"),
    path("settings/", v.SettingsView.as_view(), name="crm-settings"),
    path("reasons/", v.ReasonsView.as_view(), name="crm-reasons"),
    path("reasons/<int:pk>/", v.ReasonDetailView.as_view(), name="crm-reason"),
    path("templates/", v.TemplatesView.as_view(), name="crm-templates"),
    path("templates/<int:pk>/", v.TemplateDetailView.as_view(), name="crm-template"),
    path("tags/", v.TagsView.as_view(), name="crm-tags"),
    path("tags/<int:pk>/", v.TagDetailView.as_view(), name="crm-tag"),
]
