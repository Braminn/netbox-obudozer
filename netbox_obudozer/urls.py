"""
URL маршруты плагина netbox_obudozer

Использует NetBox-специфичные утилиты для автоматической генерации URL patterns.
"""
from django.urls import include, path
from utilities.urls import get_model_urls
from . import views

urlpatterns = [
    # Синхронизация с vCenter
    path('sync-vcenter/', views.sync_vcenter_view, name='sync_vcenter'),

    # Автоматическая генерация URL для ObuServices (list, add, bulk_edit, bulk_delete)
    path('obu-services/', include(get_model_urls('netbox_obudozer', 'obuservices', detail=False))),

    # Автоматическая генерация URL для ObuServices (detail, edit, delete)
    path('obu-services/<int:pk>/', include(get_model_urls('netbox_obudozer', 'obuservices'))),
]
