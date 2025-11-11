"""
URL маршруты плагина netbox_obudozer

Определяет все URL endpoints для плагина.
"""
from django.urls import path
from . import views

urlpatterns = [
    # Список VM
    path('vm-records/', views.VMRecordListView.as_view(), name='vmrecord_list'),
    
    # Детальная страница VM
    path('vm-records/<int:pk>/', views.VMRecordView.as_view(), name='vmrecord'),
    
    # Создание VM
    path('vm-records/add/', views.VMRecordEditView.as_view(), name='vmrecord_add'),
    
    # Редактирование VM
    path('vm-records/<int:pk>/edit/', views.VMRecordEditView.as_view(), name='vmrecord_edit'),
    
    # Удаление VM
    path('vm-records/<int:pk>/delete/', views.VMRecordDeleteView.as_view(), name='vmrecord_delete'),
    
    # Массовое удаление VM
    path('vm-records/delete/', views.VMRecordBulkDeleteView.as_view(), name='vmrecord_bulk_delete'),
    
    # Синхронизация с vCenter
    path('sync-vcenter/', views.sync_vcenter_view, name='sync_vcenter'),
]
