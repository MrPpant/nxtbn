from django.urls import path
from nxtbn.core.api.dashboard import views as core_views
from nxtbn.core.api.dashboard.status import views as status_views

urlpatterns = [
    path('site-settings/', core_views.SiteSettingsView.as_view(), name='site-settings'),
    path('invoice-settings/<int:pk>/', core_views.InvoiceSettingsView.as_view(), name='invoice-settings'),
    path('invoice-settings/upload-logo/<int:id>/', core_views.InvoiceSettingsLogoUploadAPIView.as_view(), name='upload-logo'),

    path('system-status/', status_views.SystemStatusAPIView.as_view(), name='system-status'),
    path('db-tables-details/', status_views.DatabaseTableInfoAPIView.as_view(), name='db-details'),
    path('language-list/', core_views.LanguageChoicesAPIView.as_view(), name='language-list'),
]
