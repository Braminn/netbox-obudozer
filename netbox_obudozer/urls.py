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

    # BusinessService URLs
    path('business-services/', views.BusinessServiceListView.as_view(), name='businessservice_list'),
    path('business-services/add/', views.BusinessServiceEditView.as_view(), name='businessservice_add'),
    path('business-services/<int:pk>/', views.BusinessServiceView.as_view(), name='businessservice'),
    path('business-services/<int:pk>/edit/', views.BusinessServiceEditView.as_view(), name='businessservice_edit'),
    path('business-services/<int:pk>/delete/', views.BusinessServiceDeleteView.as_view(), name='businessservice_delete'),

    # BusinessService Bulk Operations
    path('business-services/import/', views.BusinessServiceBulkImportView.as_view(), name='businessservice_import'),
    path('business-services/edit/', views.BusinessServiceBulkEditView.as_view(), name='businessservice_bulk_edit'),
    path('business-services/delete/', views.BusinessServiceBulkDeleteView.as_view(), name='businessservice_bulk_delete'),

    # ServiceVMAssignment URLs
    path('vm-assignments/', views.ServiceVMAssignmentListView.as_view(), name='servicevmassignment_list'),
    path('vm-assignments/add/', views.ServiceVMAssignmentEditView.as_view(), name='servicevmassignment_add'),
    path('vm-assignments/<int:pk>/edit/', views.ServiceVMAssignmentEditView.as_view(), name='servicevmassignment_edit'),
    path('vm-assignments/<int:pk>/delete/', views.ServiceVMAssignmentDeleteView.as_view(), name='servicevmassignment_delete'),
]
