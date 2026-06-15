from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from accounts.permissions import IsAdmin
from .models import LegalDocument, ComplianceRule, ComplianceViolation, AttendanceRecord
from .serializers import LegalDocumentSerializer, ComplianceRuleSerializer, ComplianceViolationSerializer
from django.utils import timezone

class LegalDocumentViewSet(viewsets.ModelViewSet):
    queryset = LegalDocument.objects.all()
    serializer_class = LegalDocumentSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['doc_type', 'status']

    @action(detail=True, methods=['post'])
    def sign(self, request, pk=None):
        doc = self.get_object()
        if doc.status == 'SIGNED':
            return Response({'error': 'Hujjat allaqachon imzolangan.'}, status=400)
        
        doc.status = 'SIGNED'
        doc.signed_by = request.user
        doc.signed_at = timezone.now()
        doc.digital_signature = request.data.get('signature', 'SIMULATED_SIGNATURE')
        doc.save()
        return Response(self.get_serializer(doc).data)

class ComplianceRuleViewSet(viewsets.ModelViewSet):
    queryset = ComplianceRule.objects.all()
    serializer_class = ComplianceRuleSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['rule_type', 'is_active', 'severity']

class ComplianceViolationViewSet(viewsets.ModelViewSet):
    queryset = ComplianceViolation.objects.all()
    serializer_class = ComplianceViolationSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_resolved', 'rule__severity']

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None):
        violation = self.get_object()
        if violation.is_resolved:
            return Response({'error': 'Allaqachon hal qilingan.'}, status=400)
        
        violation.is_resolved = True
        violation.resolved_by = request.user
        violation.resolution_note = request.data.get('note', '')
        violation.save()
        return Response(self.get_serializer(violation).data)


from rest_framework import serializers as drf_serializers

class AttendanceSerializer(drf_serializers.ModelSerializer):
    employee_name = drf_serializers.SerializerMethodField()

    class Meta:
        model = AttendanceRecord
        fields = '__all__'
        read_only_fields = ('recorded_by',)

    def get_employee_name(self, obj) -> str:
        return obj.employee.full_name or obj.employee.username


class AttendanceViewSet(viewsets.ModelViewSet):
    queryset = AttendanceRecord.objects.select_related('employee').all()
    serializer_class = AttendanceSerializer
    permission_classes = [IsAdmin]
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['employee', 'date', 'status']

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)
