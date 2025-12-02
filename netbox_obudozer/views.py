"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter.
CRUD операции для VirtualMachine используют стандартные NetBox views.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse

from .sync import get_sync_status
from .jobs import VCenterSyncJob


@permission_required('virtualization.add_virtualmachine')
def sync_vcenter_view(request):
    """
    View для запуска синхронизации с vCenter.

    GET: Отображает статус синхронизации
    POST: Ставит задачу синхронизации в очередь и возвращает JSON с job_id

    Args:
        request: HTTP request объект

    Returns:
        HttpResponse или JsonResponse
    """
    if request.method == 'POST':
        try:
            # Ставим задачу в очередь
            job = VCenterSyncJob.enqueue()

            # Возвращаем JSON с ID задачи
            return JsonResponse({
                'success': True,
                'job_id': job.pk,
                'message': f'Задача синхронизации #{job.pk} поставлена в очередь'
            })

        except Exception as e:
            # Критическая ошибка постановки в очередь
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    # GET запрос - показываем статус синхронизации
    sync_status = get_sync_status()

    return render(request, 'netbox_obudozer/sync_status.html', {
        'sync_status': sync_status,
    })


#
# BusinessService Views
#

from netbox.views import generic
from django.db.models import Count
from . import models, tables, forms, filtersets


class BusinessServiceListView(generic.ObjectListView):
    """
    Отображает список бизнес-сервисов с фильтрацией и поиском.
    """
    queryset = models.BusinessService.objects.select_related(
        'organization'
    ).prefetch_related(
        'tags',
        'vm_assignments__virtual_machine'
    ).annotate(
        vm_count=Count('vm_assignments')
    )
    table = tables.BusinessServiceTable
    filterset = filtersets.BusinessServiceFilterSet
    filterset_form = forms.BusinessServiceFilterForm


class BusinessServiceView(generic.ObjectView):
    """
    Отображает детальную информацию о бизнес-сервисе.
    Включает список привязанных VM.
    """
    queryset = models.BusinessService.objects.select_related(
        'organization'
    ).prefetch_related(
        'tags',
        'vm_assignments__virtual_machine__cluster',
    )

    def get_extra_context(self, request, instance):
        # Получаем привязки VM с дополнительной информацией
        vm_assignments = instance.vm_assignments.select_related(
            'virtual_machine',
            'virtual_machine__cluster',
        ).all()

        # Подсчет VM
        vm_count = vm_assignments.count()

        return {
            'vm_assignments': vm_assignments,
            'vm_count': vm_count,
        }


class BusinessServiceEditView(generic.ObjectEditView):
    """
    Создание или редактирование бизнес-сервиса.
    """
    queryset = models.BusinessService.objects.all()
    form = forms.BusinessServiceForm


class BusinessServiceDeleteView(generic.ObjectDeleteView):
    """
    Удаление бизнес-сервиса.
    Привязки VM удаляются автоматически (CASCADE).
    """
    queryset = models.BusinessService.objects.all()


class BusinessServiceChangeLogView(generic.ObjectChangeLogView):
    """
    История изменений бизнес-сервиса.
    """
    queryset = models.BusinessService.objects.all()


class BusinessServiceBulkImportView(generic.BulkImportView):
    """
    Массовый импорт бизнес-сервисов из CSV.
    """
    queryset = models.BusinessService.objects.all()
    model_form = forms.BusinessServiceForm


class BusinessServiceBulkEditView(generic.BulkEditView):
    """
    Массовое редактирование бизнес-сервисов.
    """
    queryset = models.BusinessService.objects.select_related('organization').prefetch_related('tags')
    filterset = filtersets.BusinessServiceFilterSet
    table = tables.BusinessServiceTable
    form = forms.BusinessServiceBulkEditForm


class BusinessServiceBulkDeleteView(generic.BulkDeleteView):
    """
    Массовое удаление бизнес-сервисов.
    """
    queryset = models.BusinessService.objects.select_related('organization').prefetch_related('tags')
    filterset = filtersets.BusinessServiceFilterSet
    table = tables.BusinessServiceTable


#
# ServiceVMAssignment Views
#

class ServiceVMAssignmentListView(generic.ObjectListView):
    """
    Отображает список всех привязок VM к сервисам.
    """
    queryset = models.ServiceVMAssignment.objects.select_related(
        'service',
        'service__organization',
        'virtual_machine',
        'virtual_machine__cluster'
    )
    table = tables.ServiceVMAssignmentTable
    filterset = filtersets.ServiceVMAssignmentFilterSet


class ServiceVMAssignmentEditView(generic.ObjectEditView):
    """
    Создание или редактирование привязки VM к сервису.
    """
    queryset = models.ServiceVMAssignment.objects.all()
    form = forms.ServiceVMAssignmentForm


class ServiceVMAssignmentDeleteView(generic.ObjectDeleteView):
    """
    Удаление привязки VM от сервиса.
    """
    queryset = models.ServiceVMAssignment.objects.all()
