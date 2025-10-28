from netbox.api.routers import NetBoxRouter
from .views import VMRecordViewSet

router = NetBoxRouter()
router.register('vm-records', VMRecordViewSet)

urlpatterns = router.urls
