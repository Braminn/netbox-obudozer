"""
API URL маршруты для плагина netbox_obudozer

Регистрирует ViewSet'ы в роутере для автоматической генерации REST API endpoints.
"""
from rest_framework import routers
from .views import ObuServicesViewSet


# Создаем роутер для автоматической регистрации ViewSet'ов
router = routers.DefaultRouter()

# Регистрируем ViewSet для ObuServices
# Это создаст следующие endpoints:
# - GET    /api/plugins/netbox-obudozer/obu-services/       - список
# - POST   /api/plugins/netbox-obudozer/obu-services/       - создание
# - GET    /api/plugins/netbox-obudozer/obu-services/{id}/  - детали
# - PUT    /api/plugins/netbox-obudozer/obu-services/{id}/  - полное обновление
# - PATCH  /api/plugins/netbox-obudozer/obu-services/{id}/  - частичное обновление
# - DELETE /api/plugins/netbox-obudozer/obu-services/{id}/  - удаление
router.register('obu-services', ObuServicesViewSet)

# Экспортируем URL patterns из роутера
urlpatterns = router.urls
