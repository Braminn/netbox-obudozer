import django_filters
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from tenancy.models import Tenant
from virtualization.models import VirtualMachine
from .models import BusinessService, ServiceVMAssignment


class BusinessServiceFilterSet(NetBoxModelFilterSet):
    """
    FilterSet для модели BusinessService.
    Обеспечивает фильтрацию по всем ключевым полям.
    """
    organization_id = django_filters.ModelMultipleChoiceFilter(
        queryset=Tenant.objects.all(),
        label='Organization (ID)',
    )

    organization = django_filters.ModelMultipleChoiceFilter(
        field_name='organization__slug',
        queryset=Tenant.objects.all(),
        to_field_name='slug',
        label='Organization (slug)',
    )

    status = django_filters.MultipleChoiceFilter(
        choices=BusinessService.StatusChoices.choices,
        null_value=None,
        label='Статус'
    )

    responsible_person = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Ответственное лицо'
    )

    request_number = django_filters.CharFilter(
        lookup_expr='icontains',
        label='Номер заявки'
    )

    # Фильтры по дате начала договора
    contract_start_date = django_filters.DateFilter(
        label='Дата начала договора'
    )
    contract_start_date_after = django_filters.DateFilter(
        field_name='contract_start_date',
        lookup_expr='gte',
        label='Дата начала договора (после)'
    )
    contract_start_date_before = django_filters.DateFilter(
        field_name='contract_start_date',
        lookup_expr='lte',
        label='Дата начала договора (до)'
    )

    # Фильтры по дате окончания договора
    contract_end_date = django_filters.DateFilter(
        label='Дата окончания договора'
    )
    contract_end_date_after = django_filters.DateFilter(
        field_name='contract_end_date',
        lookup_expr='gte',
        label='Дата окончания договора (после)'
    )
    contract_end_date_before = django_filters.DateFilter(
        field_name='contract_end_date',
        lookup_expr='lte',
        label='Дата окончания договора (до)'
    )

    # Фильтр по дате истечения договора (для удобства)
    contract_expiring_soon = django_filters.BooleanFilter(
        method='filter_expiring_soon',
        label='Истекает в ближайшие 90 дней'
    )

    class Meta:
        model = BusinessService
        fields = ['id', 'name', 'description']

    def search(self, queryset, name, value):
        """
        Кастомный поиск по нескольким полям.
        """
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value) |
            Q(responsible_person__icontains=value) |
            Q(request_number__icontains=value) |
            Q(organization__name__icontains=value)
        )

    def filter_expiring_soon(self, queryset, name, value):
        """
        Фильтр для договоров, истекающих в ближайшие 90 дней.
        """
        if value:
            from datetime import date, timedelta
            today = date.today()
            expiry_date = today + timedelta(days=90)
            return queryset.filter(
                contract_end_date__gte=today,
                contract_end_date__lte=expiry_date,
                status=BusinessService.StatusChoices.ACTIVE
            )
        return queryset


class ServiceVMAssignmentFilterSet(django_filters.FilterSet):
    """
    FilterSet для модели ServiceVMAssignment.

    Использует базовый FilterSet, так как ServiceVMAssignment
    наследует models.Model, а не NetBoxModel.
    """
    service_id = django_filters.ModelMultipleChoiceFilter(
        queryset=BusinessService.objects.all(),
        label='Service (ID)',
    )

    service = django_filters.ModelMultipleChoiceFilter(
        field_name='service__name',
        queryset=BusinessService.objects.all(),
        to_field_name='name',
        label='Service (name)',
    )

    virtual_machine_id = django_filters.ModelMultipleChoiceFilter(
        queryset=VirtualMachine.objects.all(),
        label='VM (ID)',
    )

    virtual_machine = django_filters.ModelMultipleChoiceFilter(
        field_name='virtual_machine__name',
        queryset=VirtualMachine.objects.all(),
        to_field_name='name',
        label='VM (name)',
    )

    assigned_date = django_filters.DateFilter(
        label='Дата назначения'
    )
    assigned_date_after = django_filters.DateFilter(
        field_name='assigned_date',
        lookup_expr='gte',
        label='Дата назначения (после)'
    )
    assigned_date_before = django_filters.DateFilter(
        field_name='assigned_date',
        lookup_expr='lte',
        label='Дата назначения (до)'
    )

    q = django_filters.CharFilter(
        method='filter_search',
        label='Поиск'
    )

    class Meta:
        model = ServiceVMAssignment
        fields = ['id', 'service', 'virtual_machine', 'assigned_date']

    def filter_search(self, queryset, name, value):
        """
        Кастомный поиск по нескольким полям.
        """
        if not value.strip():
            return queryset
        return queryset.filter(
            Q(service__name__icontains=value) |
            Q(virtual_machine__name__icontains=value) |
            Q(notes__icontains=value)
        )
