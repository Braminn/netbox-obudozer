from netbox.plugins import PluginTemplateExtension


class TenantResourcesExtension(PluginTemplateExtension):
    models = ['tenancy.tenant']

    def right_page(self):
        from django.db.models import Sum
        from virtualization.models import VirtualMachine, VirtualDisk

        tenant = self.context['object']

        active_vms = VirtualMachine.objects.filter(tenant=tenant, status='active')
        active_vm_ids = active_vms.values_list('id', flat=True)

        totals = active_vms.aggregate(
            total_vcpus=Sum('vcpus'),
            total_memory=Sum('memory'),
        )

        disk_sum = VirtualDisk.objects.filter(virtual_machine_id__in=active_vm_ids).aggregate(
            total=Sum('size')
        )
        total_disk_mb = disk_sum['total'] or 0

        def fmt_memory(mb):
            if mb >= 1024 * 1024:
                return f"{mb / 1024 / 1024:.1f} ТБ"
            if mb >= 1024:
                return f"{mb / 1024:.1f} ГБ"
            return f"{mb} МБ"

        def fmt_disk(mb):
            if mb >= 1000 * 1000:
                return f"{mb / 1000 / 1000:.1f} ТБ"
            if mb >= 1000:
                return f"{mb / 1000:.1f} ГБ"
            return f"{mb} МБ"

        return self.render('netbox_obudozer/inc/tenant_resources.html', extra_context={
            'total_vcpus': int(totals['total_vcpus'] or 0),
            'total_memory': fmt_memory(totals['total_memory'] or 0),
            'total_disk': fmt_disk(total_disk_mb),
        })


template_extensions = [TenantResourcesExtension]
