"""
URL маршруты плагина netbox_obudozer

Определяет URL endpoints для синхронизации с vCenter.
CRUD операции для VirtualMachine используют стандартные NetBox endpoints.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Синхронизация с vCenter
    path('sync-vcenter/', views.sync_vcenter_view, name='sync_vcenter'),

    # Список услуг OBU
    path('obu-services/', views.ObuServicesListView.as_view(), name='obuservices_list'),
]
