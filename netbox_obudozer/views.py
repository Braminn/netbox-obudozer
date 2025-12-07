"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter и полный CRUD для услуг OBU.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse
from django.db.models import Count

from netbox.views.generic import (
    ObjectListView,
    ObjectView,
    ObjectEditView,
    ObjectDeleteView,
    BulkEditView,
    BulkDeleteView,
)
from utilities.views import register_model_view, ViewTab

from .sync import get_sync_status
from .jobs import VCenterSyncJob
from .models import ObuServices
from .tables import ObuServicesTable
from .forms import ObuServicesForm, ObuServicesBulkEditForm
from .filtersets import ObuServicesFilterSet


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

            # Получаем все VM с assignments
            vms = VirtualMachine.objects.filter(
                service_assignments__isnull=False
            ).distinct()

            updated_cf = 0
            updated_tenant = 0

            for vm in vms:
                # Синхронизация custom field obu_services
                service_ids = list(
                    vm.service_assignments.values_list('service_id', flat=True)
                    .order_by('service_id')
                )
                vm.custom_field_data['obu_services'] = service_ids
                updated_cf += 1

                # Синхронизация tenant от первой услуги с tenant
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

                vm.save()

            return JsonResponse({
                'success': True,
                'updated_cf': updated_cf,
                'updated_tenant': updated_tenant,
                'message': f'Обновлено: {updated_cf} VM с custom field, {updated_tenant} VM с tenant'
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


@register_model_view(ObuServices, name='contacts')
class ObuServicesContactsView(ObjectView):
    """
    Представление для отображения контактов услуги OBU.

    Показывает таблицу ContactAssignment, привязанных к данной услуге.
    Позволяет просматривать назначенные контакты с их ролями, приоритетами
    и контактной информацией.
    """
    queryset = ObuServices.objects.all()
    template_name = 'netbox_obudozer/obuservices_contacts.html'

    tab = ViewTab(
        label='Контакты',
        badge=lambda obj: obj.contact_assignments.count(),
        permission='tenancy.view_contactassignment',
        weight=500
    )

    def get_extra_context(self, request, instance):
        """
        Добавляет ContactAssignment в контекст шаблона.

        Args:
            request: HTTP request объект
            instance: экземпляр ObuServices

        Returns:
            dict с дополнительным контекстом
        """
        from django.contrib.contenttypes.models import ContentType
        from tenancy.models import ContactAssignment

        content_type = ContentType.objects.get_for_model(ObuServices)
        contact_assignments = ContactAssignment.objects.filter(
            object_type=content_type,
            object_id=instance.pk
        ).select_related('contact', 'role')

        return {
            'contact_assignments': contact_assignments,
        }
