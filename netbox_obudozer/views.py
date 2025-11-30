"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter.
CRUD операции для VirtualMachine используют стандартные NetBox views.
"""
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import permission_required

from .sync import get_sync_status
from .jobs import VCenterSyncJob


@permission_required('virtualization.add_virtualmachine')
def sync_vcenter_view(request):
    """
    View для запуска синхронизации с vCenter.

    GET: Отображает статус синхронизации
    POST: Ставит задачу синхронизации в очередь и перенаправляет на страницу job

    Args:
        request: HTTP request объект

    Returns:
        HttpResponse или HttpResponseRedirect
    """
    if request.method == 'POST':
        try:
            # Ставим задачу в очередь
            job = VCenterSyncJob.enqueue()

            # Сообщаем пользователю
            messages.success(
                request,
                f"✅ Задача синхронизации поставлена в очередь (Job #{job.pk}). "
                f"Перенаправляю на страницу выполнения..."
            )

            # Перенаправляем на страницу job в NetBox
            return redirect('core:job', pk=job.pk)

        except Exception as e:
            # Критическая ошибка постановки в очередь
            messages.error(
                request,
                f"❌ Ошибка при постановке задачи в очередь: {str(e)}"
            )
            return redirect('plugins:netbox_obudozer:sync_vcenter')

    # GET запрос - показываем статус синхронизации
    sync_status = get_sync_status()

    return render(request, 'netbox_obudozer/sync_status.html', {
        'sync_status': sync_status,
    })
