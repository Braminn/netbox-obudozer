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
