from netbox.plugins import PluginTemplateExtension


class TenantResourcesExtension(PluginTemplateExtension):
    models = ['tenancy.tenant']

    def right_page(self):
        from virtualization.models import VirtualMachine
        from .resources import vm_resources

        tenant = self.context['object']

        return self.render(
            'netbox_obudozer/inc/tenant_resources.html',
            extra_context=vm_resources(VirtualMachine.objects.filter(tenant=tenant)),
        )


template_extensions = [TenantResourcesExtension]
