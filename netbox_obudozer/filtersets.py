import django_filters
from netbox.filtersets import NetBoxModelFilterSet
from .models import VMRecord


class VMRecordFilterSet(NetBoxModelFilterSet):
    """Набор фильтров для VM записей"""

    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name (contains)'
    )

    state = django_filters.ChoiceFilter(
        choices=VMRecord.STATE_CHOICES,
        label='State'
    )

    class Meta:
        model = VMRecord
        fields = ['id', 'name', 'state']
