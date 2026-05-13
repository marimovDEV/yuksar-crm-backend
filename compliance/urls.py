from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LegalDocumentViewSet, ComplianceRuleViewSet, ComplianceViolationViewSet, AttendanceViewSet

router = DefaultRouter()
router.register(r'documents', LegalDocumentViewSet)
router.register(r'rules', ComplianceRuleViewSet)
router.register(r'violations', ComplianceViolationViewSet)
router.register(r'attendance', AttendanceViewSet, basename='attendance')

urlpatterns = [
    path('', include(router.urls)),
]
