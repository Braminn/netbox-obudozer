"""
URL маршруты REST API для плагина netbox_obudozer

Регистрирует API endpoints.
"""
from netbox.api.routers import NetBoxRouter
from .views import VMRecordViewSet

router = NetBoxRouter()
router.register('vm-records', VMRecordViewSet)

urlpatterns = router.urls
