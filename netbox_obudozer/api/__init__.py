"""
API модуль плагина netbox_obudozer

Экспортирует сериализаторы и ViewSet'ы для использования NetBox.
"""
from .serializers import ObuServicesSerializer
from .views import ObuServicesViewSet

__all__ = [
    'ObuServicesSerializer',
    'ObuServicesViewSet',
]
