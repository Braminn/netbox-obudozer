"""
REST API для плагина netbox_obudozer

Экспортирует сериализаторы и viewsets для использования в API.
"""
from .serializers import VMRecordSerializer
from .views import VMRecordViewSet

__all__ = ['VMRecordSerializer', 'VMRecordViewSet']
