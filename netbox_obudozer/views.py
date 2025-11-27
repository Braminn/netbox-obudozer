"""
Views (представления) плагина netbox_obudozer

Содержит все view-классы для работы с VM Records и функции синхронизации.
"""
from django.contrib import messages
from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required
from django.utils.html import format_html

from netbox.views import generic
from . import models, forms, tables, filtersets
from .sync import sync_vcenter_vms, get_sync_status


class VMRecordListView(generic.ObjectListView):
    """
    View для отображения списка VM Records.

    Отображает таблицу со всеми виртуальными машинами.
    Поддерживает фильтрацию и поиск.
    """
    queryset = models.VMRecord.objects.all()
    table = tables.VMRecordTable
    filterset = filtersets.VMRecordFilterSet
    template_name = 'netbox_obudozer/vmrecord_list.html'

    def get_extra_context(self, request):
        """
        Добавляет дополнительный контекст для шаблона.

        Передает статус синхронизации для отображения в UI.
        """
        context = super().get_extra_context(request)
        context['sync_status'] = get_sync_status()
        return context


class VMRecordView(generic.ObjectView):
    """
    View для отображения детальной информации о VM Record.
    """
    queryset = models.VMRecord.objects.all()


class VMRecordEditView(generic.ObjectEditView):
    """
    View для создания и редактирования VM Record.
    """
    queryset = models.VMRecord.objects.all()
    form = forms.VMRecordForm


class VMRecordDeleteView(generic.ObjectDeleteView):
    """
    View для удаления VM Record.
    """
    queryset = models.VMRecord.objects.all()


class VMRecordBulkDeleteView(generic.BulkDeleteView):
    """
    View для массового удаления VM Records.
    """
    queryset = models.VMRecord.objects.all()
    table = tables.VMRecordTable


@login_required
def sync_vcenter_view(request):
    """
    View для запуска синхронизации с vCenter из интерфейса.

    Выполняет синхронизацию и перенаправляет обратно на список VM
    с сообщением о результатах.

    Args:
        request: HTTP request объект

    Returns:
        HttpResponseRedirect: Перенаправление на список VM
    """
    try:
        # Выполняем синхронизацию
        result = sync_vcenter_vms()
        
        # Формируем сообщение с результатами
        if result.errors:
            # Есть ошибки
            error_msg = format_html(
                "Синхронизация завершена с ошибками.<br>"
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
                "✅ Синхронизация выполнена успешно за {} сек.<br>"
                "Создано: {}, Обновлено: {}, Без изменений: {}, Помечено отсутствующими: {}",
                duration_formatted,
                result.created,
                result.updated,
                result.unchanged,
                result.marked_missing
            )
            messages.success(request, success_msg)
        
    except Exception as e:
        # Критическая ошибка
        messages.error(request, f"Критическая ошибка при синхронизации: {str(e)}")
    
    # Перенаправляем обратно на список VM
    return redirect('plugins:netbox_obudozer:vmrecord_list')
