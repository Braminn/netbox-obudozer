"""
URL маршруты плагина netbox_obudozer

Определяет URL endpoints для синхронизации с vCenter и CRUD операций для услуг OBU.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Синхронизация с vCenter
    path('sync-vcenter/', views.sync_vcenter_view, name='sync_vcenter'),

    # Список услуг OBU
    path(
        'obu-services/',
        views.ObuServicesListView.as_view(),
        name='obuservices_list'
    ),

    # Создание новой услуги
    path(
        'obu-services/add/',
        views.ObuServicesCreateView.as_view(),
        name='obuservices_add'
    ),

    # Просмотр деталей услуги
    path(
        'obu-services/<int:pk>/',
        views.ObuServicesDetailView.as_view(),
        name='obuservices'
    ),

    # Редактирование услуги
    path(
        'obu-services/<int:pk>/edit/',
        views.ObuServicesEditView.as_view(),
        name='obuservices_edit'
    ),

    # Удаление услуги
    path(
        'obu-services/<int:pk>/delete/',
        views.ObuServicesDeleteView.as_view(),
        name='obuservices_delete'
    ),

    # Массовое редактирование
    path(
        'obu-services/edit/',
        views.ObuServicesBulkEditView.as_view(),
        name='obuservices_bulk_edit'
    ),

    # Массовое удаление
    path(
        'obu-services/delete/',
        views.ObuServicesBulkDeleteView.as_view(),
        name='obuservices_bulk_delete'
    ),
]
