"""
Выявление проблем услуг OBU и запись их в custom field услуги.

Архитектура:
- Каждая проверка — класс-наследник ServiceCheck с кодом, лейблом и цветом.
  Метод evaluate() получает список услуг пачкой и возвращает pk проблемных.
- Реестр SERVICE_CHECKS — единственное место, где перечислены проверки.
  Из него же собирается ChoiceSet для multiselect-поля service_problems,
  поэтому новая проверка = новый класс + строка в реестре.
- recalc_service_problems() прогоняет все проверки и записывает в CF
  service_problems список кодов. Пишутся только изменившиеся услуги и через
  QuerySet.update(): без записей в changelog и без сигналов post_save
  (иначе сработал бы sync_tenant_to_vms на каждую услугу).

Результат хранится в БД (а не считается на лету), чтобы по нему работали
стандартные фильтры NetBox: ?cf_service_problems=service_expired.
"""
from datetime import date

from django.utils import timezone

# Имя custom field со списком проблем услуги (multiselect)
SERVICE_PROBLEMS_FIELD = 'service_problems'

# Custom field «Действует до» (date) — создан вручную в NetBox, плагин его не создаёт
SERVICE_DATE_END_FIELD = 'date_end'


# ──────────────────────────────────────────────────────────────────────────────
# Проверки
# ──────────────────────────────────────────────────────────────────────────────

class ServiceCheck:
    """
    Базовый класс проверки услуги.

    code  — значение в multiselect (стабильный идентификатор, не менять после релиза)
    label — человекочитаемое название, показывается в UI
    color — цвет варианта в ChoiceSet (имена цветов NetBox: red, orange, ...)
    """
    code = None
    label = None
    color = 'red'

    def evaluate(self, services, today):
        """
        Args:
            services: список ObuServices (с загруженным custom_field_data)
            today: текущая дата (передаётся снаружи, чтобы все проверки
                   одного прогона видели одну и ту же дату)

        Returns:
            set[int] — pk услуг, у которых проблема есть
        """
        raise NotImplementedError


def _parse_date(value):
    """Дата из custom_field_data (там она хранится строкой 'YYYY-MM-DD')."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


class ServiceExpiredCheck(ServiceCheck):
    """«Действует до» в прошлом."""
    code = 'service_expired'
    label = 'Истёк срок действия'
    color = 'red'

    def evaluate(self, services, today):
        result = set()
        for service in services:
            date_end = _parse_date(service.custom_field_data.get(SERVICE_DATE_END_FIELD))
            if date_end and date_end < today:
                result.add(service.pk)
        return result


class ServiceNoEndDateCheck(ServiceCheck):
    """«Действует до» не заполнено."""
    code = 'service_no_end_date'
    label = 'Не указан срок действия'
    color = 'orange'

    def evaluate(self, services, today):
        return {
            service.pk for service in services
            if not service.custom_field_data.get(SERVICE_DATE_END_FIELD)
        }


# Реестр проверок услуг. Порядок задаёт порядок кодов в поле service_problems.
SERVICE_CHECKS = [
    ServiceExpiredCheck(),
    ServiceNoEndDateCheck(),
]


# ──────────────────────────────────────────────────────────────────────────────
# Пересчёт
# ──────────────────────────────────────────────────────────────────────────────

def recalc_service_problems(services=None, logger=None):
    """
    Пересчитывает проблемы услуг и записывает их в CF service_problems.

    Args:
        services: queryset ObuServices для пересчёта (по умолчанию — все)
        logger: опциональный logger (JobRunner.logger)

    Returns:
        dict: total — проверено услуг, with_problems — из них с проблемами,
              updated — у скольких список проблем изменился
    """
    from .custom_fields import ensure_service_custom_fields
    from .models import ObuServices

    ensure_service_custom_fields()

    if services is None:
        services = ObuServices.objects.all()
    services = list(services.only('pk', 'custom_field_data'))

    today = timezone.localdate()

    # pk услуги → множество кодов проблем
    problems = {service.pk: set() for service in services}
    for check in SERVICE_CHECKS:
        for pk in check.evaluate(services, today):
            problems[pk].add(check.code)

    order = [check.code for check in SERVICE_CHECKS]
    updated = 0
    for service in services:
        new_value = [code for code in order if code in problems[service.pk]] or None
        old_value = service.custom_field_data.get(SERVICE_PROBLEMS_FIELD) or None
        if new_value == old_value:
            continue

        data = dict(service.custom_field_data)
        data[SERVICE_PROBLEMS_FIELD] = new_value
        # update() вместо save(): без changelog и без сигналов post_save
        ObuServices.objects.filter(pk=service.pk).update(custom_field_data=data)
        updated += 1

    stats = {
        'total': len(services),
        'with_problems': sum(1 for codes in problems.values() if codes),
        'updated': updated,
    }
    if logger:
        logger.info(
            f"  ✓ Проблемы услуг пересчитаны: с проблемами {stats['with_problems']} "
            f"из {stats['total']}, изменено {stats['updated']}"
        )
    return stats
