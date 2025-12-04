"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter и полный CRUD для услуг OBU.
"""
from django.shortcuts import render
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse

from netbox.views.generic import (
    ObjectListView,
    ObjectView,  # Используется для detail view
    ObjectEditView,
    ObjectDeleteView,
    BulkEditView,
    BulkDeleteView,
)

from .sync import get_sync_status
from .jobs import VCenterSyncJob
from .models import ObuServices
from .tables import ObuServicesTable
from .forms import ObuServicesForm


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
    queryset = ObuServices.objects.all()
    table = ObuServicesTable


class ObuServicesDetailView(ObjectView):
    """
    Представление для просмотра деталей услуги OBU.

    Отображает полную информацию о конкретной услуге,
    включая пользовательские поля и теги.
    """
    queryset = ObuServices.objects.all()


class ObuServicesCreateView(ObjectEditView):
    """
    Представление для создания новой услуги OBU.
    """
    queryset = ObuServices.objects.all()
    form_class = ObuServicesForm
    default_return_url = 'plugins:netbox_obudozer:obuservices_list'


class ObuServicesEditView(ObjectEditView):
    """
    Представление для редактирования услуги OBU.

    Позволяет изменять все поля услуги, включая пользовательские поля и теги.
    Все изменения автоматически логируются через ObjectChange.
    """
    queryset = ObuServices.objects.all()
    form_class = ObuServicesForm
    default_return_url = 'plugins:netbox_obudozer:obuservices_list'


class ObuServicesDeleteView(ObjectDeleteView):
    """
    Представление для удаления услуги OBU.

    Запрашивает подтверждение перед удалением и отображает
    все связанные объекты, которые также будут удалены.
    """
    queryset = ObuServices.objects.all()
    default_return_url = 'plugins:netbox_obudozer:obuservices_list'


class ObuServicesBulkEditView(BulkEditView):
    """
    Представление для массового редактирования услуг OBU.

    Позволяет одновременно изменять выбранные услуги.
    """
    queryset = ObuServices.objects.all()
    table = ObuServicesTable
    form_class = ObuServicesForm


class ObuServicesBulkDeleteView(BulkDeleteView):
    """
    Представление для массового удаления услуг OBU.

    Позволяет одновременно удалить несколько выбранных услуг.
    """
    queryset = ObuServices.objects.all()
    table = ObuServicesTable
