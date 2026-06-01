from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PLCDeviceViewSet, PLCTagViewSet, TelemetryHistorianViewSet

router = DefaultRouter()
router.register(r'devices', PLCDeviceViewSet)
router.register(r'tags', PLCTagViewSet)
router.register(r'history', TelemetryHistorianViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
