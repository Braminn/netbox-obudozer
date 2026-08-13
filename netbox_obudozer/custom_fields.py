"""
Создание и привязка Custom Fields плагина netbox_obudozer.

Вынесено из sync.py: поля создаются в фазе подготовки синхронизации, но к
логике самого сравнения/применения изменений отношения не имеют.

Точка входа — ensure_custom_fields(). Все функции идемпотентны
(get_or_create + add), вызывать можно сколько угодно раз.

Исключение: поля nginx-импорта живут в nginx_import.py
(_ensure_nginx_custom_fields), т.к. создаются в своём процессе импорта.
"""
from django.contrib.contenttypes.models import ContentType
from extras.models import CustomField, CustomFieldChoiceSet


# Custom field "Порядок восстановления ВМ" (vm_restore_order).
# Значения берутся из CustomFieldChoiceSet:
#   '1' - экстренный, '2' - желательно, '3' - базовый, '4' - не включать.
# При синхронизации всем ВМ с ПУСТЫМ полем проставляется базовый ('3'),
# заполненное значение НЕ перезаписывается (см. sync.ensure_restore_order_default).
RESTORE_ORDER_FIELD = 'vm_restore_order'
RESTORE_ORDER_DEFAULT = '3'


# ──────────────────────────────────────────────────────────────────────────────
# VirtualMachine
# ──────────────────────────────────────────────────────────────────────────────

# Простые поля, заполняемые данными из vCenter при синхронизации
_VM_FIELDS_SPEC = [
    ('vcenter_id', {
        'label': 'vCenter ID',
        'type': 'text',
        'description': 'Уникальный идентификатор VM в vCenter',
        'required': False,
    }),
    ('last_synced', {
        'label': 'Last Synced',
        'type': 'datetime',
        'description': 'Время последней синхронизации с vCenter',
        'required': False,
    }),
    ('vcenter_cluster', {
        'label': 'vCenter Cluster',
        'type': 'text',
        'description': 'Имя кластера vCenter, в котором находится ВМ',
        'required': False,
    }),
    ('ip_address', {
        'label': 'IP Address',
        'type': 'text',
        'description': 'Primary IP address from vCenter (guest.ipAddress)',
        'required': False,
    }),
    ('tools_status', {
        'label': 'VMware Tools Status',
        'type': 'text',
        'description': 'VMware Tools status from guest.toolsStatus',
        'required': False,
    }),
    ('vmtools_description', {
        'label': 'VMware Tools Description',
        'type': 'text',
        'description': 'VMware Tools description from guestinfo.vmtools.description',
        'required': False,
    }),
    ('vmtools_version_number', {
        'label': 'VMware Tools Version Number',
        'type': 'text',
        'description': 'VMware Tools version number from guestinfo.vmtools.versionNumber',
        'required': False,
    }),
    ('os_pretty_name', {
        'label': 'OS Pretty Name',
        'type': 'text',
        'description': 'OS pretty name from guestInfo.detailed.data (e.g., "Ubuntu 22.04.3 LTS")',
        'required': False,
    }),
    ('os_family_name', {
        'label': 'OS Family Name',
        'type': 'text',
        'description': 'OS family name from guestInfo.detailed.data (e.g., "Linux")',
        'required': False,
    }),
    ('os_distro_name', {
        'label': 'OS Distro Name',
        'type': 'text',
        'description': 'OS distribution name from guestInfo.detailed.data (e.g., "ubuntu")',
        'required': False,
    }),
    ('os_distro_version', {
        'label': 'OS Distro Version',
        'type': 'text',
        'description': 'OS distribution version from guestInfo.detailed.data (e.g., "22.04")',
        'required': False,
    }),
    ('os_kernel_version', {
        'label': 'OS Kernel Version',
        'type': 'text',
        'description': 'OS kernel version from guestInfo.detailed.data (e.g., "5.15.0-91-generic")',
        'required': False,
    }),
    ('os_bitness', {
        'label': 'OS Bitness',
        'type': 'text',
        'description': 'OS bitness from guestInfo.detailed.data (e.g., "64")',
        'required': False,
    }),
    ('creation_date', {
        'label': 'Creation Date',
        'type': 'datetime',
        'description': 'VM creation date from config.createDate',
        'required': False,
    }),
    ('has_obu_services', {
        'label': 'Имеет OBU сервис',
        'type': 'boolean',
        'description': 'True если у виртуальной машины есть хотя бы одна привязанная услуга OBU',
        'required': False,
        'ui_visible': 'always',
        'ui_editable': 'no',
    }),
]


def _ensure_restore_order_field():
    """Поле «Приоритет восстановления ВМ» (select) вместе с набором вариантов."""
    choiceset, _ = CustomFieldChoiceSet.objects.get_or_create(
        name='Приоритет восстановления ВМ',
        defaults={
            'extra_choices': [
                ['1', '1 - экстренный'],
                ['2', '2 - важный'],
                ['3', '3 - базовый'],
                ['4', '4 - не включать'],
            ],
            'choice_colors': {
                '1': 'red',
                '2': 'orange',
                '3': 'green',
                '4': 'gray',
            },
        }
    )

    field, _ = CustomField.objects.get_or_create(
        name=RESTORE_ORDER_FIELD,
        defaults={
            'label': 'Приоритет восстановления ВМ',
            'type': 'select',
            'description': 'Приоритет восстановления виртуальной машины',
            'required': False,
            'choice_set': choiceset,
        }
    )
    return field


def _ensure_obu_services_field():
    """Multiobject-поле со списком услуг OBU, привязанных к ВМ (read-only)."""
    from .models import ObuServices

    field, created = CustomField.objects.get_or_create(
        name='obu_services',
        defaults={
            'label': 'OBU Services',
            'type': 'multiobject',
            'description': 'Услуги, к которым привязана виртуальная машина',
            'required': False,
            'ui_visible': 'always',
            'ui_editable': 'no',  # Read-only, управляется через ServiceVMAssignment
        }
    )

    # related_object_type задаётся отдельно, а не через defaults (см. CLAUDE.md)
    if created or not field.related_object_type:
        field.related_object_type = ContentType.objects.get_for_model(ObuServices)
        field.save()

    return field


def ensure_vm_custom_fields():
    """Создаёт и привязывает к VirtualMachine все поля плагина."""
    from virtualization.models import VirtualMachine

    fields = [
        CustomField.objects.get_or_create(name=name, defaults=defaults)[0]
        for name, defaults in _VM_FIELDS_SPEC
    ]
    fields.append(_ensure_restore_order_field())
    fields.append(_ensure_obu_services_field())

    vm_ct = ContentType.objects.get_for_model(VirtualMachine)
    for field in fields:
        if vm_ct not in field.object_types.all():
            field.object_types.add(vm_ct)


# ──────────────────────────────────────────────────────────────────────────────
# Contact
# ──────────────────────────────────────────────────────────────────────────────

def ensure_contact_custom_fields():
    """
    Создаёт и привязывает к tenancy.Contact поля плагина.

    rutoken_cert заполняется вручную и отдаётся наружу через
    /api/plugins/obudozer/rutoken-access/ (см. rutoken.py).
    """
    from tenancy.models import Contact
    from .rutoken import RUTOKEN_CERT_FIELD

    field, _ = CustomField.objects.get_or_create(
        name=RUTOKEN_CERT_FIELD,
        defaults={
            'label': 'Rutoken ID',
            'type': 'text',
            'description': 'Идентификатор Rutoken-сертификата контакта',
            'required': False,
        }
    )

    contact_ct = ContentType.objects.get_for_model(Contact)
    if contact_ct not in field.object_types.all():
        field.object_types.add(contact_ct)


# ──────────────────────────────────────────────────────────────────────────────
# Точка входа
# ──────────────────────────────────────────────────────────────────────────────

def ensure_custom_fields(logger=None):
    """Создаёт все custom fields плагина. Вызывается в фазе подготовки синхронизации."""
    ensure_vm_custom_fields()
    ensure_contact_custom_fields()

    if logger:
        logger.info("  ✓ Custom Fields готовы")
