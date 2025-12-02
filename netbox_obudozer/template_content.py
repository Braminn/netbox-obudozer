"""
Template extensions для плагина netbox_obudozer

Расширяет стандартные страницы NetBox дополнительным контентом.
"""
from netbox.plugins import PluginTemplateExtension


class VirtualMachineBusinessServices(PluginTemplateExtension):
    """
    Добавляет панель с бизнес-сервисами на страницу детального просмотра VM.
    """
    model = 'virtualization.virtualmachine'

    def right_page(self):
        """
        Добавляет панель бизнес-сервисов в правую колонку страницы VM.
        """
        # Импортируем модель внутри метода, чтобы избежать проблем с AppRegistryNotReady
        from .models import ServiceVMAssignment

        # Получаем привязки сервисов для данной VM
        assignments = ServiceVMAssignment.objects.filter(
            virtual_machine=self.context['object']
        ).select_related(
            'service',
            'service__organization'
        ).order_by('service__name')

        return self.render('netbox_obudozer/inc/vm_services_panel.html', extra_context={
            'assignments': assignments,
        })


# Регистрируем расширения
template_extensions = [VirtualMachineBusinessServices]
