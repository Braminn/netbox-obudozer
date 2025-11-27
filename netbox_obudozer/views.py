"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter.
CRUD операции для VirtualMachine используют стандартные NetBox views.
"""
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import permission_required
from django.utils.html import format_html

from .sync import sync_vcenter_vms, get_sync_status


@permission_required('virtualization.add_virtualmachine')
def sync_vcenter_view(request):
    """
    View для запуска синхронизации с vCenter.

    GET: Отображает статус синхронизации
    POST: Запускает синхронизацию

    Args:
        request: HTTP request объект

    Returns:
        HttpResponse или HttpResponseRedirect
    """
    if request.method == 'POST':
        try:
            # Выполняем синхронизацию
            result = sync_vcenter_vms()

            # Формируем сообщение с результатами
            if result.errors:
                # Есть ошибки
                error_msg = format_html(
                    "❌ Синхронизация завершена с ошибками.<br>"
                    "Создано: {}, Обновлено: {}, Помечено отсутствующими: {}<br>"
                    "Ошибок: {}",
                    result.created,
                    result.updated,
                    result.marked_missing,
                    len(result.errors)
                )
                messages.warning(request, error_msg)

                # Добавляем детали ошибок
                for error in result.errors[:5]:  # Показываем первые 5 ошибок
                    messages.error(request, error)
            else:
                # Успешная синхронизация
                duration_seconds = float(result.duration) if result.duration else 0.0
                # Форматируем число заранее (format_html не поддерживает :f формат)
                duration_formatted = f"{duration_seconds:.2f}"
                success_msg = format_html(
                    "✅ Синхронизация завершена за {} сек.<br>"
                    "Создано: {}, Обновлено: {}, Без изменений: {}, "
                    "Помечено отсутствующими: {}",
                    duration_formatted,
                    result.created,
                    result.updated,
                    result.unchanged,
                    result.marked_missing
                )
                messages.success(request, success_msg)

        except Exception as e:
            # Критическая ошибка
            messages.error(request, f"❌ Критическая ошибка при синхронизации: {str(e)}")

        # Перенаправляем обратно на страницу синхронизации
        return redirect('plugins:netbox_obudozer:sync_vcenter')

    # GET запрос - показываем статус синхронизации
    sync_status = get_sync_status()

    return render(request, 'netbox_obudozer/sync_status.html', {
        'sync_status': sync_status,
    })
