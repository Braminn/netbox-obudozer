"""
Выявление проблем услуг OBU и виртуальных машин и запись их в custom fields.

Архитектура:
- Проверка — класс-наследник ProblemCheck с кодом, лейблом и цветом.
  Метод evaluate() получает список объектов пачкой и возвращает pk проблемных.
- Цель (ProblemTarget) — модель + multiselect-поле, куда пишутся коды проблем,
  + ChoiceSet для этого поля + список проверок. Сейчас цели две:
  SERVICE_TARGET (ObuServices → service_problems) и VM_TARGET (VirtualMachine → vm_problems).
- Новая проверка = новый класс + строка в списке checks нужной цели.
  ChoiceSet поля собирается из этого же списка (см. custom_fields.ensure_problems_field).
- recalc_problems() прогоняет проверки цели и записывает список кодов в её поле.
  Пишутся только изменившиеся объекты и через bulk_update(): без записей
  в changelog и без сигналов post_save (иначе, например, сработал бы
  sync_tenant_to_vms на каждую услугу).

Результат хранится в БД (а не считается на лету), чтобы по нему работали
стандартные фильтры NetBox: ?cf_service_problems=service_expired.
"""
from datetime import date

from django.apps import apps
from django.utils import timezone

# Custom field «Действует до» (date) у услуги — создан вручную в NetBox, плагин его не создаёт
SERVICE_DATE_END_FIELD = 'date_end'

# Custom field с названием ОС у ВМ — заполняется синхронизацией vCenter
VM_OS_FIELD = 'os_pretty_name'


# ──────────────────────────────────────────────────────────────────────────────
# Базовые классы
# ──────────────────────────────────────────────────────────────────────────────

class ProblemCheck:
    """
    Базовый класс проверки.

    code  — значение в multiselect (стабильный идентификатор, не менять после релиза)
    label — человекочитаемое название, показывается в UI
    color — цвет варианта в ChoiceSet (имена цветов NetBox: red, orange, ...)
    """
    code = None
    label = None
    color = 'red'

    def evaluate(self, objects, today):
        """
        Args:
            objects: список объектов цели (с загруженным custom_field_data)
            today: текущая дата (передаётся снаружи, чтобы все проверки
                   одного прогона видели одну и ту же дату)

        Returns:
            set[int] — pk объектов, у которых проблема есть
        """
        raise NotImplementedError


class ProblemTarget:
    """Модель, в multiselect-поле которой пишутся коды проблем, и её проверки."""

    def __init__(self, model, field, label, description, choiceset, checks):
        self.model_label = model          # 'app_label.ModelName' — модель берём лениво
        self.field = field
        self.label = label
        self.description = description
        self.choiceset = choiceset
        self.checks = checks

    @property
    def model(self):
        return apps.get_model(self.model_label)


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


# ──────────────────────────────────────────────────────────────────────────────
# Проверки услуг
# ──────────────────────────────────────────────────────────────────────────────

class ServiceExpiredCheck(ProblemCheck):
    """«Действует до» в прошлом."""
    code = 'service_expired'
    label = 'Истёк срок действия'
    color = 'red'

    def evaluate(self, objects, today):
        result = set()
        for service in objects:
            date_end = _parse_date(service.custom_field_data.get(SERVICE_DATE_END_FIELD))
            if date_end and date_end < today:
                result.add(service.pk)
        return result


class ServiceNoEndDateCheck(ProblemCheck):
    """«Действует до» не заполнено."""
    code = 'service_no_end_date'
    label = 'Не указан срок действия'
    color = 'orange'

    def evaluate(self, objects, today):
        return {
            service.pk for service in objects
            if not service.custom_field_data.get(SERVICE_DATE_END_FIELD)
        }


# ──────────────────────────────────────────────────────────────────────────────
# Проверки ВМ
# ──────────────────────────────────────────────────────────────────────────────

class VMOsUnknownCheck(ProblemCheck):
    """OS Pretty Name пустое (обычно нет VMware Tools или ВМ заведена вручную)."""
    code = 'vm_os_unknown'
    label = 'ОС не определена'
    color = 'orange'

    def evaluate(self, objects, today):
        return {
            vm.pk for vm in objects
            if not (vm.custom_field_data.get(VM_OS_FIELD) or '').strip()
        }


def _vms_with_os_status(objects, today, status):
    """
    pk ВМ, у которых OS Pretty Name совпадает с записью реестра OperatingSystem
    в статусе status ('expired' / 'soon', см. OperatingSystem.eol_status_on).
    ОС без записи в реестре или без eol_date проблемой не считаются.
    """
    from .models import OperatingSystem

    os_names = {
        os.name for os in OperatingSystem.objects.exclude(eol_date__isnull=True)
        if os.eol_status_on(today) == status
    }
    if not os_names:
        return set()
    return {vm.pk for vm in objects if vm.custom_field_data.get(VM_OS_FIELD) in os_names}


class VMOsEolCheck(ProblemCheck):
    """Дата окончания поддержки ОС (OperatingSystem.eol_date) в прошлом."""
    code = 'vm_os_eol'
    label = 'Закончилась поддержка ОС'
    color = 'red'

    def evaluate(self, objects, today):
        return _vms_with_os_status(objects, today, 'expired')


class VMOsEolSoonCheck(ProblemCheck):
    """До окончания поддержки ОС осталось не больше eol_warning_days дней."""
    code = 'vm_os_eol_soon'
    label = 'Скоро закончится поддержка ОС'
    color = 'yellow'

    def evaluate(self, objects, today):
        return _vms_with_os_status(objects, today, 'soon')


# ──────────────────────────────────────────────────────────────────────────────
# Цели (реестр). Порядок checks задаёт порядок кодов в поле.
# ──────────────────────────────────────────────────────────────────────────────

SERVICE_TARGET = ProblemTarget(
    model='netbox_obudozer.ObuServices',
    field='service_problems',
    label='Проблемы сервиса',
    description='Выявленные проблемы услуги (заполняется автоматически, см. problems.py)',
    choiceset='Проблемы услуг OBU',
    checks=[
        ServiceExpiredCheck(),
        ServiceNoEndDateCheck(),
    ],
)

VM_TARGET = ProblemTarget(
    model='virtualization.VirtualMachine',
    field='vm_problems',
    label='Проблемы ВМ',
    description='Выявленные проблемы виртуальной машины (заполняется автоматически, см. problems.py)',
    choiceset='Проблемы ВМ',
    checks=[
        VMOsUnknownCheck(),
        VMOsEolCheck(),
        VMOsEolSoonCheck(),
    ],
)

PROBLEM_TARGETS = [SERVICE_TARGET, VM_TARGET]

# Обратная совместимость с кодом, импортирующим имя поля услуги
SERVICE_PROBLEMS_FIELD = SERVICE_TARGET.field


# ──────────────────────────────────────────────────────────────────────────────
# Пересчёт
# ──────────────────────────────────────────────────────────────────────────────

def recalc_problems(target, queryset=None, logger=None):
    """
    Пересчитывает проблемы объектов цели и записывает их в её custom field.

    Args:
        target: ProblemTarget
        queryset: объекты для пересчёта (по умолчанию — все объекты модели цели)
        logger: опциональный logger (JobRunner.logger)

    Returns:
        dict: total — проверено объектов, with_problems — из них с проблемами,
              updated — у скольких список проблем изменился
    """
    from .custom_fields import ensure_problems_field

    ensure_problems_field(target)

    model = target.model
    if queryset is None:
        queryset = model.objects.all()
    objects = list(queryset.only('pk', 'custom_field_data'))

    today = timezone.localdate()

    # pk объекта → множество кодов проблем
    problems = {obj.pk: set() for obj in objects}
    for check in target.checks:
        for pk in check.evaluate(objects, today):
            problems[pk].add(check.code)

    order = [check.code for check in target.checks]
    changed = []
    for obj in objects:
        new_value = [code for code in order if code in problems[obj.pk]] or None
        old_value = obj.custom_field_data.get(target.field) or None
        if new_value == old_value:
            continue
        obj.custom_field_data = dict(obj.custom_field_data)
        obj.custom_field_data[target.field] = new_value
        changed.append(obj)

    # bulk_update вместо save(): без changelog и без сигналов post_save
    if changed:
        model.objects.bulk_update(changed, ['custom_field_data'], batch_size=500)

    stats = {
        'total': len(objects),
        'with_problems': sum(1 for codes in problems.values() if codes),
        'updated': len(changed),
    }
    if logger:
        logger.info(
            f"  ✓ {target.label}: с проблемами {stats['with_problems']} "
            f"из {stats['total']}, изменено {stats['updated']}"
        )
    return stats


def recalc_service_problems(queryset=None, logger=None):
    """Пересчёт проблем услуг (CF service_problems)."""
    return recalc_problems(SERVICE_TARGET, queryset, logger)


def recalc_vm_problems(queryset=None, logger=None):
    """Пересчёт проблем ВМ (CF vm_problems)."""
    return recalc_problems(VM_TARGET, queryset, logger)


def recalc_all_problems(logger=None):
    """
    Пересчёт проблем всех целей.

    Порядок важен на будущее: сначала ВМ, потом услуги — услуги будут
    наследовать проблемы своих ВМ.
    """
    return {
        'vm': recalc_vm_problems(logger=logger),
        'service': recalc_service_problems(logger=logger),
    }
