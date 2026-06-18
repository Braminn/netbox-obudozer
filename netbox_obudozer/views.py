"""
Views (представления) плагина netbox_obudozer

Содержит функцию синхронизации с vCenter и полный CRUD для услуг OBU.
"""
from django.shortcuts import render, redirect
from django.contrib import messages
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
from .models import ObuServices, NginxDomain
from .tables import ObuServicesTable, NginxDomainTable
from .forms import ObuServicesForm, ObuServicesBulkEditForm
from .filtersets import ObuServicesFilterSet, NginxDomainFilterSet


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


@permission_required('netbox_obudozer.view_vcentersyncaccess')
def test_gitlab_connection_view(request):
    """
    Проверка подключения к GitLab. POST → результат через messages → redirect обратно.
    Поддерживает несколько репозиториев через gitlab_projects (список).
    """
    if request.method == 'POST':
        try:
            from django.conf import settings
            import requests as req

            config = settings.PLUGINS_CONFIG.get('netbox_obudozer', {})
            gitlab_url = config.get('gitlab_url', '').rstrip('/')
            gitlab_token = config.get('gitlab_token', '')
            gitlab_projects = config.get('gitlab_projects', [])
            verify_ssl = config.get('gitlab_verify_ssl', True)

            if not gitlab_url:
                messages.error(request, 'GitLab: gitlab_url не настроен в PLUGINS_CONFIG')
                return redirect('plugins:netbox_obudozer:sync_vcenter')
            if not gitlab_token:
                messages.error(request, 'GitLab: gitlab_token не настроен в PLUGINS_CONFIG')
                return redirect('plugins:netbox_obudozer:sync_vcenter')

            headers = {'PRIVATE-TOKEN': gitlab_token}
            kwargs = {'headers': headers, 'timeout': 10, 'verify': verify_ssl}

            # Проверяем сам токен
            token_resp = req.get(f'{gitlab_url}/api/v4/personal_access_tokens/self', **kwargs)
            if token_resp.status_code == 401:
                messages.error(request, 'GitLab: неверный токен (HTTP 401 Unauthorized)')
                return redirect('plugins:netbox_obudozer:sync_vcenter')
            if token_resp.status_code == 200:
                token_name = token_resp.json().get('name', '?')
                messages.success(request, f'GitLab: токен «{token_name}» действителен')
            else:
                messages.warning(request, f'GitLab: токен принят, но /personal_access_tokens/self вернул HTTP {token_resp.status_code}')

            if not gitlab_projects:
                messages.warning(request, 'GitLab: gitlab_projects не настроен в PLUGINS_CONFIG')
                return redirect('plugins:netbox_obudozer:sync_vcenter')

            # Проверяем каждый репозиторий
            for project_id in gitlab_projects:
                project_id_encoded = str(project_id).replace('/', '%2F')
                proj_resp = req.get(f'{gitlab_url}/api/v4/projects/{project_id_encoded}', **kwargs)

                if proj_resp.status_code != 200:
                    messages.error(request, f'GitLab [{project_id}]: недоступен (HTTP {proj_resp.status_code})')
                    continue

                p = proj_resp.json()
                last_activity = (p.get('last_activity_at', '') or '')[:10]
                messages.success(request, (
                    f'GitLab [{p["name_with_namespace"]}]: '
                    f'ветка: {p.get("default_branch", "?")} | '
                    f'последняя активность: {last_activity}'
                ))

        except Exception as e:
            messages.error(request, f'GitLab: {e}')

    return redirect('plugins:netbox_obudozer:sync_vcenter')


@permission_required('netbox_obudozer.view_vcentersyncaccess')
def gitlab_debug_view(request):
    """
    Отладочная страница: загружает .conf файлы из GitLab, парсит их и
    показывает результат по каждому файлу без сохранения в БД.
    """
    results_by_file = None
    project_reports = None
    domain_table = None
    stats = None
    error = None

    if request.method == 'POST':
        try:
            from collections import defaultdict
            from .gitlab_client import fetch_nginx_configs
            from .nginx_parser import parse_configs

            configs_raw, project_reports = fetch_nginx_configs()
            resolutions = parse_configs(configs_raw)

            from django.conf import settings as _settings
            waf_ips = set(_settings.PLUGINS_CONFIG.get('netbox_obudozer', {}).get('waf_ips', []))

            # Обогащаем каждый результат: строим targets_display для каждого backend
            processed = []
            for r in resolutions:
                targets_display = []
                for t in r.targets:
                    chain_parts = list(t.chain)
                    if t.ip:
                        ip_str = t.ip
                        if t.port:
                            ip_str += f':{t.port}'
                        chain_parts.append(ip_str)
                        status = 'chained' if len(t.chain) > 1 else 'direct'
                    elif t.is_loop:
                        status = 'loop'
                    elif t.upstream_name:
                        chain_parts.append(f'[upstream: {t.upstream_name}]')
                        status = 'upstream'
                    else:
                        chain_parts.append('[не разрешён]')
                        status = 'unresolved'
                    targets_display.append({
                        'chain_display': ' → '.join(chain_parts),
                        'status': status,
                    })

                is_waf = bool(waf_ips) and any(t.ip in waf_ips for t in r.targets if t.ip)

                processed.append({
                    'domain': r.domain,
                    'aliases': r.aliases,
                    'targets': targets_display,
                    'is_waf': is_waf,
                    'source_file': r.source_file,
                    'source_project': r.source_project,
                })

            # Группируем по проекту → список файлов → список доменов
            by_project = defaultdict(lambda: defaultdict(list))
            for item in processed:
                by_project[item['source_project']][item['source_file']].append(item)

            # Преобразуем в список для удобства итерации в шаблоне
            results_by_file = [
                {
                    'project': project,
                    'files': [
                        {'path': file_path, 'domains': domains}
                        for file_path, domains in sorted(files.items())
                    ],
                }
                for project, files in sorted(by_project.items())
            ]

            unique_domains = {r.domain for r in resolutions}
            stats = {
                'total_files': len(configs_raw),
                'total_domains': len(unique_domains),
                'resolved': sum(
                    1 for d in unique_domains
                    if any(t.ip for r in resolutions if r.domain == d for t in r.targets)
                ),
                'upstream': sum(
                    1 for d in unique_domains
                    if not any(t.ip for r in resolutions if r.domain == d for t in r.targets)
                    and any(t.upstream_name for r in resolutions if r.domain == d for t in r.targets)
                ),
                'unresolved': sum(
                    1 for d in unique_domains
                    if not any(
                        t.ip or t.upstream_name
                        for r in resolutions if r.domain == d
                        for t in r.targets
                    )
                ),
            }

            # Агрегация по доменному имени: один домен — все вхождения по файлам
            domain_rows = {}
            for item in processed:
                domain = item['domain']
                if domain not in domain_rows:
                    domain_rows[domain] = {'domain': domain, 'occurrences': [], 'is_waf': False}
                domain_rows[domain]['occurrences'].append({
                    'source_file': item['source_file'],
                    'source_project': item['source_project'],
                    'targets': item['targets'],
                })
                if item['is_waf']:
                    domain_rows[domain]['is_waf'] = True
            domain_table = sorted(domain_rows.values(), key=lambda x: x['domain'])

        except Exception as e:
            import traceback
            error = f'{e}\n\n{traceback.format_exc()}'

    return render(request, 'netbox_obudozer/gitlab_debug.html', {
        'results_by_file': results_by_file,
        'project_reports': project_reports,
        'domain_table': domain_table,
        'stats': stats,
        'error': error,
    })


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


# ──────────────────────────────────────────────────────────────────────────────
# NginxDomain views
# ──────────────────────────────────────────────────────────────────────────────

@register_model_view(NginxDomain, 'list', detail=False)
class NginxDomainListView(ObjectListView):
    queryset = NginxDomain.objects.all()
    table = NginxDomainTable
    filterset = NginxDomainFilterSet


@register_model_view(NginxDomain)
class NginxDomainDetailView(ObjectView):
    queryset = NginxDomain.objects.all()


@register_model_view(NginxDomain, 'bulk_delete', detail=False)
class NginxDomainBulkDeleteView(BulkDeleteView):
    queryset = NginxDomain.objects.all()
    table = NginxDomainTable


def import_nginx_domains_view(request):
    """POST — запускает импорт доменов из GitLab и возвращает JSON со статистикой."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    try:
        from .nginx_import import import_nginx_domains
        result = import_nginx_domains()
        return JsonResponse({
            'success': True,
            'created': result['created'],
            'updated': result['updated'],
            'skipped': result['skipped'],
            'errors': result['errors'],
        })
    except Exception as e:
        import traceback
        return JsonResponse({'success': False, 'error': str(e), 'traceback': traceback.format_exc()}, status=500)
