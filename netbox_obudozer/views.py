"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter и полный CRUD для услуг OBU.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse
from django.db.models import Count, Sum

from netbox.views.generic import (
    ObjectListView,
    ObjectView,
    ObjectEditView,
    ObjectDeleteView,
    BulkEditView,
    BulkDeleteView,
)
from utilities.views import register_model_view

from .sync import get_sync_status
from .jobs import VCenterSyncJob
from .models import ObuServices
from .tables import ObuServicesTable
from .forms import ObuServicesForm, ObuServicesBulkEditForm
from .filtersets import ObuServicesFilterSet


@permission_required('netbox_obudozer.view_vcentersyncaccess')
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


@permission_required('virtualization.view_virtualmachine')
def sync_services_cf_view(request):
    """
    View для синхронизации custom field obu_services и tenant.

    Обновляет custom field 'obu_services' и tenant для всех VM с привязанными сервисами.
    Используется для первичной инициализации после деплоя или ресинхронизации.

    POST: Выполняет синхронизацию и возвращает JSON с результатом

    Args:
        request: HTTP request объект

    Returns:
        JsonResponse с результатом синхронизации
    """
    if request.method == 'POST':
        try:
            from virtualization.models import VirtualMachine
            from .models import ServiceVMAssignment, ObuServices

            # Собираем ID всех VM, у которых есть assignments
            vms_with_services_ids = set(
                ServiceVMAssignment.objects.values_list('virtual_machine_id', flat=True).distinct()
            )

            updated_cf = 0
            updated_tenant = 0
            updated_flag = 0

            # Обновляем VM с сервисами
            vms_with = VirtualMachine.objects.filter(id__in=vms_with_services_ids)
            for vm in vms_with:
                service_ids = list(
                    vm.service_assignments.values_list('service_id', flat=True)
                    .order_by('service_id')
                )
                vm.custom_field_data['obu_services'] = service_ids
                vm.custom_field_data['has_obu_services'] = True
                updated_cf += 1
                updated_flag += 1

                first_service_with_tenant = (
                    vm.service_assignments
                    .filter(service__tenant__isnull=False)
                    .select_related('service__tenant')
                    .first()
                )
                if first_service_with_tenant:
                    vm.tenant = first_service_with_tenant.service.tenant
                    updated_tenant += 1
                else:
                    vm.tenant = None

                first_service_with_role = (
                    vm.service_assignments
                    .filter(service__vm_role__isnull=False)
                    .select_related('service__vm_role')
                    .first()
                )
                if first_service_with_role:
                    vm.role = first_service_with_role.service.vm_role
                else:
                    vm.role = None

                vm.save()

            # Сбрасываем has_obu_services у VM без сервисов
            vms_without = VirtualMachine.objects.exclude(id__in=vms_with_services_ids)
            for vm in vms_without:
                vm.custom_field_data['has_obu_services'] = False
                vm.save()
                updated_flag += 1

            return JsonResponse({
                'success': True,
                'updated_cf': updated_cf,
                'updated_tenant': updated_tenant,
                'updated_flag': updated_flag,
                'message': (
                    f'Обновлено: {updated_cf} VM с obu_services, '
                    f'{updated_tenant} VM с tenant, '
                    f'{updated_flag} VM с флагом has_obu_services'
                )
            })

        except Exception as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)

    # GET не поддерживается
    return JsonResponse({'error': 'Method not allowed'}, status=405)


@register_model_view(ObuServices, 'list', detail=False)
class ObuServicesListView(ObjectListView):
    """
    Представление для отображения списка услуг OBU.

    ObjectListView автоматически предоставляет:
    - Пагинацию
    - Сортировку
    - Базовый поиск (если определен filterset)
    - Экспорт данных
    - Кнопки действий (Create, Edit, Delete, BulkEdit, BulkDelete)
    """
    queryset = ObuServices.objects.annotate(
        vm_count=Count('vm_assignments')
    )
    table = ObuServicesTable
    filterset = ObuServicesFilterSet


@register_model_view(ObuServices)
class ObuServicesDetailView(ObjectView):
    """
    Представление для просмотра деталей услуги OBU.

    Отображает полную информацию о конкретной услуге,
    включая пользовательские поля и теги.
    """
    queryset = ObuServices.objects.all()

    def get_extra_context(self, request, instance):
        from virtualization.models import VirtualMachine
        from .models import ServiceVMAssignment

        vm_ids = ServiceVMAssignment.objects.filter(service=instance).values_list('virtual_machine_id', flat=True)
        active_vm_ids = VirtualMachine.objects.filter(id__in=vm_ids, status='active').values_list('id', flat=True)
        totals = VirtualMachine.objects.filter(id__in=active_vm_ids).aggregate(
            total_vcpus=Sum('vcpus'),
            total_memory=Sum('memory'),
        )

        from virtualization.models import VirtualDisk
        disk_sum = VirtualDisk.objects.filter(virtual_machine_id__in=active_vm_ids).aggregate(total=Sum('size'))
        total_disk_mb = disk_sum['total'] or 0

        def fmt_memory(mb):
            # memory хранится в бинарных МБ (1 ГБ = 1024 МБ)
            if mb >= 1024 * 1024:
                return f"{mb / 1024 / 1024:.1f} ТБ"
            if mb >= 1024:
                return f"{mb / 1024:.1f} ГБ"
            return f"{mb} МБ"

        def fmt_disk(mb):
            # VirtualDisk.size хранится в десятичных МБ (1 ГБ = 1000 МБ, как в vCenter UI)
            if mb >= 1000 * 1000:
                return f"{mb / 1000 / 1000:.1f} ТБ"
            if mb >= 1000:
                return f"{mb / 1000:.1f} ГБ"
            return f"{mb} МБ"

        return {
            'total_vcpus': int(totals['total_vcpus'] or 0),
            'total_memory': fmt_memory(totals['total_memory'] or 0),
            'total_disk': fmt_disk(total_disk_mb),
        }


@register_model_view(ObuServices, 'add', detail=False)
@register_model_view(ObuServices, 'edit')
class ObuServicesEditView(ObjectEditView):
    """
    Представление для создания и редактирования услуг OBU.

    Используется как для создания новых услуг (add), так и для редактирования
    существующих (edit). NetBox автоматически определяет режим по наличию pk.
    """
    queryset = ObuServices.objects.all()
    form = ObuServicesForm


@register_model_view(ObuServices, 'delete')
class ObuServicesDeleteView(ObjectDeleteView):
    """
    Представление для удаления услуги OBU.

    Запрашивает подтверждение перед удалением и отображает
    все связанные объекты, которые также будут удалены.
    """
    queryset = ObuServices.objects.all()


@register_model_view(ObuServices, 'bulk_edit', detail=False)
class ObuServicesBulkEditView(BulkEditView):
    """
    Представление для массового редактирования услуг OBU.

    Позволяет одновременно изменять выбранные услуги.
    """
    queryset = ObuServices.objects.all()
    table = ObuServicesTable
    form = ObuServicesBulkEditForm


@register_model_view(ObuServices, 'bulk_delete', detail=False)
class ObuServicesBulkDeleteView(BulkDeleteView):
    """
    Представление для массового удаления услуг OBU.

    Позволяет одновременно удалить несколько выбранных услуг.
    """
    queryset = ObuServices.objects.all()
    table = ObuServicesTable
