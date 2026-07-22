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

    # Синхронизация custom field obu_services
    path('sync-services-cf/', views.sync_services_cf_view, name='sync_services_cf'),

    # Проверка подключения к GitLab
    path('test-gitlab-connection/', views.test_gitlab_connection_view, name='test_gitlab_connection'),

    # Отладочная страница парсинга nginx-конфигов из GitLab
    path('gitlab-debug/', views.gitlab_debug_view, name='gitlab_debug'),

    # Автоматическая генерация URL для ObuServices (list, add, bulk_edit, bulk_delete)
    path('obu-services/', include(get_model_urls('netbox_obudozer', 'obuservices', detail=False))),

    # Автоматическая генерация URL для ObuServices (detail, edit, delete)
    path('obu-services/<int:pk>/', include(get_model_urls('netbox_obudozer', 'obuservices'))),

    # Nginx domains
    path('nginx-domains/', include(get_model_urls('netbox_obudozer', 'nginxdomain', detail=False))),
    path('nginx-domains/<int:pk>/', include(get_model_urls('netbox_obudozer', 'nginxdomain'))),
    path('import-nginx-domains/', views.import_nginx_domains_view, name='import_nginx_domains'),
]
