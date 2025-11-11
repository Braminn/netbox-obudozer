"""
Фильтры для плагина netbox_obudozer

Определяет наборы фильтров для поиска и фильтрации VM Records.
"""
import django_filters
from netbox.filtersets import NetBoxModelFilterSet
from .models import VMRecord


class VMRecordFilterSet(NetBoxModelFilterSet):
    """
    Набор фильтров для VM Records.
    
    Позволяет фильтровать VM по различным критериям.
    """
    
    name = django_filters.CharFilter(
        field_name='name',
        lookup_expr='icontains',
        label='Name (contains)'
    )
    
    state = django_filters.ChoiceFilter(
        choices=VMRecord.STATE_CHOICES,
        label='State'
    )
    
    vcenter_id = django_filters.CharFilter(
        field_name='vcenter_id',
        lookup_expr='icontains',
        label='vCenter ID'
    )
    
    exist = django_filters.BooleanFilter(
        label='Exists in vCenter'
    )

    class Meta:
        model = VMRecord
        fields = ['id', 'name', 'state', 'vcenter_id', 'exist']

    def search(self, queryset, name, value):
        """
        Полнотекстовый поиск по нескольким полям.
        """
        if not value.strip():
            return queryset
        return queryset.filter(
            name__icontains=value
        ) | queryset.filter(
            vcenter_id__icontains=value
        )
