from django.urls import path
from . import views

urlpatterns = [
    path('vm-records/', views.VMRecordListView.as_view(), name='vmrecord_list'),
    path('vm-records/<int:pk>/', views.VMRecordView.as_view(), name='vmrecord'),
    path('vm-records/add/', views.VMRecordEditView.as_view(), name='vmrecord_add'),
    path('vm-records/<int:pk>/edit/', views.VMRecordEditView.as_view(), name='vmrecord_edit'),
    path('vm-records/<int:pk>/delete/', views.VMRecordDeleteView.as_view(), name='vmrecord_delete'),
    path('vm-records/delete/', views.VMRecordBulkDeleteView.as_view(), name='vmrecord_bulk_delete'),
]
