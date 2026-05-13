from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from .models import Lead, LeadActivity
from .serializers import LeadSerializer, LeadListSerializer, LeadActivitySerializer


class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return LeadListSerializer
        return LeadSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        status_param = self.request.query_params.get('status')
        source = self.request.query_params.get('source')
        assigned = self.request.query_params.get('assigned_to')
        if status_param:
            qs = qs.filter(status=status_param)
        if source:
            qs = qs.filter(source=source)
        if assigned:
            qs = qs.filter(assigned_to_id=assigned)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def add_activity(self, request, pk=None):
        lead = self.get_object()
        serializer = LeadActivitySerializer(data=request.data)
        if serializer.is_valid():
            serializer.save(lead=lead, created_by=request.user)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        lead = self.get_object()
        lead.status = 'WON'
        lead.save(update_fields=['status'])
        return Response({'detail': 'Lead converted to customer', 'id': lead.id})
