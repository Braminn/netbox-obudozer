"""
Импорт nginx-доменов из GitLab в модель NginxDomain.

Фазы (аналогично sync.py для vCenter):
  1. _ensure_nginx_custom_fields() — создать/привязать custom fields к NginxDomain
  2. Загрузка конфигов из GitLab и парсинг
  3. Группировка по доменному имени + вычисление агрегатов
  4. Diff (to_create / to_update / to_skip)
  5. Apply (bulk_create новых, save обновлённых, в транзакции)
"""
from django.db import transaction
from django.contrib.contenttypes.models import ContentType
from extras.models import CustomField

from .gitlab_client import fetch_nginx_configs
from .nginx_parser import parse_configs

# ──────────────────────────────────────────────────────────────────────────────
# Вспомогательные функции
# ──────────────────────────────────────────────────────────────────────────────

_STATUS_PRIORITY = ('direct', 'chained', 'upstream', 'loop', 'unresolved')


def _target_status(t):
    if t.get('is_loop'):
        return 'loop'
    if t.get('ip'):
        return 'chained' if len(t.get('chain', [])) > 1 else 'direct'
    if t.get('upstream_name'):
        return 'upstream'
    return 'unresolved'


def _best_status(all_targets):
    """Лучший статус (наивысший приоритет) среди всех targets."""
    if not all_targets:
        return 'unresolved'
    found = {_target_status(t) for t in all_targets}
    for s in _STATUS_PRIORITY:
        if s in found:
            return s
    return 'unresolved'


def _chain_display(t):
    """Строка chain_display для одного target (аналог views.py)."""
    parts = list(t.get('chain', []))
    if t.get('is_loop'):
        parts.append('[петля]')
    elif t.get('ip'):
        ip_str = t['ip']
        if t.get('port'):
            ip_str += f":{t['port']}"
        parts.append(ip_str)
    elif t.get('upstream_name'):
        parts.append(f"[upstream: {t['upstream_name']}]")
    else:
        parts.append('[не разрешён]')
    return ' → '.join(parts)


def _build_targets_text(all_targets):
    """Многострочная строка chain_display — по одной цепочке на строку (без дублей)."""
    seen = set()
    lines = []
    for t in all_targets:
        line = _chain_display(t)
        if line not in seen:
            seen.add(line)
            lines.append(line)
    return '\n'.join(lines)


def _build_configs_text(resolutions):
    """Список source_project/source_file, по одному на строку (без дублей)."""
    seen = set()
    lines = []
    for r in resolutions:
        entry = f"{r.source_project}/{r.source_file}" if r.source_project else r.source_file
        if entry not in seen:
            seen.add(entry)
            lines.append(entry)
    return '\n'.join(lines)


def _resolution_targets_as_dicts(r):
    """Конвертирует ResolvedTarget dataclass в список dict для сравнения."""
    result = []
    for t in r.targets:
        result.append({
            'ip': t.ip,
            'port': t.port,
            'chain': list(t.chain),
            'upstream_name': t.upstream_name,
            'is_loop': t.is_loop,
        })
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Фаза 1 — Custom Fields
# ──────────────────────────────────────────────────────────────────────────────

def _ensure_nginx_custom_fields():
    """Создаёт custom fields для NginxDomain, если их ещё нет."""
    from .models import NginxDomain

    nginx_ct = ContentType.objects.get_for_model(NginxDomain)

    fields_spec = [
        ('nginx_is_waf', {
            'label': 'WAF',
            'type': 'boolean',
            'description': 'Трафик проходит через WAF',
            'required': False,
        }),
        ('nginx_status', {
            'label': 'Статус разрешения',
            'type': 'text',
            'description': 'Результат разрешения: direct / chained / upstream / loop / unresolved',
            'required': False,
        }),
        ('nginx_targets', {
            'label': 'Цепочки разрешения',
            'type': 'longtext',
            'description': 'IP-адреса и цепочки proxy_pass из nginx-конфигов',
            'required': False,
        }),
        ('nginx_configs', {
            'label': 'Конфигурационные файлы',
            'type': 'longtext',
            'description': 'Список project/file, в которых встречается домен',
            'required': False,
        }),
    ]

    created_fields = []
    for name, defaults in fields_spec:
        field, _ = CustomField.objects.get_or_create(name=name, defaults=defaults)
        created_fields.append(field)

    for field in created_fields:
        if nginx_ct not in field.object_types.all():
            field.object_types.add(nginx_ct)


# ──────────────────────────────────────────────────────────────────────────────
# Фаза 2–5 — основной импорт
# ──────────────────────────────────────────────────────────────────────────────

def import_nginx_domains():
    """
    Загружает nginx-конфиги из GitLab, парсит, записывает домены в БД.

    Returns:
        dict с ключами: created, updated, skipped, errors, project_reports
    """
    from django.conf import settings as _settings
    from .models import NginxDomain

    # Фаза 1 — custom fields
    _ensure_nginx_custom_fields()

    # Фаза 2 — загрузка и парсинг
    configs_raw, project_reports = fetch_nginx_configs()
    resolutions = parse_configs(configs_raw)

    waf_ips = set(_settings.PLUGINS_CONFIG.get('netbox_obudozer', {}).get('waf_ips', []))

    # Фаза 3 — группировка по доменному имени
    # domain → list[DomainResolution]
    domain_map = {}
    for r in resolutions:
        domain_map.setdefault(r.domain, []).append(r)

    # Фаза 3b — агрегируем данные для каждого домена
    # domain → {is_waf, targets_text, configs_text, status}
    aggregated = {}
    for domain, res_list in domain_map.items():
        all_targets = []
        for r in res_list:
            all_targets.extend(_resolution_targets_as_dicts(r))

        is_waf = bool(waf_ips) and any(t['ip'] in waf_ips for t in all_targets if t.get('ip'))
        targets_text = _build_targets_text(all_targets)
        configs_text = _build_configs_text(res_list)
        status = _best_status(all_targets)

        aggregated[domain] = {
            'nginx_is_waf': is_waf,
            'nginx_targets': targets_text,
            'nginx_configs': configs_text,
            'nginx_status': status,
        }

    # Фаза 4 — diff: один запрос за всеми существующими записями
    existing = {obj.domain: obj for obj in NginxDomain.objects.all()}

    to_create = []
    to_update = []
    to_skip = []

    for domain, new_cf in aggregated.items():
        if domain not in existing:
            to_create.append(NginxDomain(domain=domain, custom_field_data=new_cf))
        else:
            obj = existing[domain]
            old_cf = {k: obj.custom_field_data.get(k) for k in new_cf}
            if old_cf == new_cf:
                to_skip.append(domain)
            else:
                obj.custom_field_data.update(new_cf)
                to_update.append(obj)

    # Фаза 5 — применяем в транзакции
    errors = []
    with transaction.atomic():
        if to_create:
            NginxDomain.objects.bulk_create(to_create)
        for obj in to_update:
            try:
                obj.save()
            except Exception as e:
                errors.append(f"{obj.domain}: {e}")

    return {
        'created': len(to_create),
        'updated': len(to_update),
        'skipped': len(to_skip),
        'errors': errors,
        'project_reports': project_reports,
    }
