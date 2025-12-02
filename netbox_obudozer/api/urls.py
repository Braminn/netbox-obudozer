"""
API URLs для netbox_obudozer
"""
from netbox.api.routers import NetBoxRouter
from .views import BusinessServiceViewSet, ServiceVMAssignmentViewSet

router = NetBoxRouter()
router.register('business-services', BusinessServiceViewSet)
router.register('vm-assignments', ServiceVMAssignmentViewSet)

urlpatterns = router.urls
