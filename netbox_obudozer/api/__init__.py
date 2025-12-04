"""
API модуль плагина netbox_obudozer

Экспортирует сериализаторы для использования NetBox.
"""
from .serializers import ObuServicesSerializer

__all__ = [
    'ObuServicesSerializer',
]
