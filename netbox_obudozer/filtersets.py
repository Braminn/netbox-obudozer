"""
FilterSets для плагина netbox_obudozer

Определяет фильтры для поиска и фильтрации объектов в UI и API.
"""
from django.db.models import Q
from netbox.filtersets import NetBoxModelFilterSet
from .models import ObuServices


class ObuServicesFilterSet(NetBoxModelFilterSet):
    """
    FilterSet для модели ObuServices.

    Предоставляет:
    - Полнотекстовый поиск по name и description
    - Автоматическую фильтрацию по tags (через NetBoxModelFilterSet)
    """

    class Meta:
        model = ObuServices
        fields = ['id', 'name', 'description']

    def search(self, queryset, name, value):
        """Полнотекстовый поиск по name и description."""
        return queryset.filter(
            Q(name__icontains=value) |
            Q(description__icontains=value)
        )
