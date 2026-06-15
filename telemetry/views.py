from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import PLCDevice, PLCTag, TelemetryHistorian
from .serializers import PLCDeviceSerializer, PLCTagSerializer, TelemetryHistorianSerializer
from accounts.permissions import IsAdmin, IsProductionRelated, IsAdminOrDirector

class PLCDeviceViewSet(viewsets.ModelViewSet):
    """
    PLC qurilmalari — faqat admin yaratadi/o'chiradi.
    Director va ishlab chiqarish o'qiy oladi.
    """
    queryset = PLCDevice.objects.all()
    serializer_class = PLCDeviceSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrDirector() | IsProductionRelated()]
        return [IsAdmin()]

class PLCTagViewSet(viewsets.ModelViewSet):
    """
    PLC teglari — faqat admin o'zgartiradi.
    Director va ishlab chiqarish o'qiy oladi (SCADA monitoring).
    """
    queryset = PLCTag.objects.all()
    serializer_class = PLCTagSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'live']:
            return [IsAdminOrDirector() | IsProductionRelated()]
        return [IsAdmin()]

    @action(detail=False, methods=['get'])
    def live(self, request):
        """
        Returns a single unified dictionary of all tags' current values for easy SCADA integration.
        """
        tags = PLCTag.objects.all()
        data = {tag.key: {
            'value': tag.current_value,
            'name': tag.name,
            'unit': tag.unit,
            'updated_at': tag.updated_at.isoformat()
        } for tag in tags}

        # Add basic active machines stats & counts
        data['active_prefoamers'] = 1 if data.get('pv1_steam_pressure', {}).get('value', 0) > 0.1 else 0
        data['active_molders'] = 1 if data.get('bf12_steam_pressure', {}).get('value', 0) > 0.1 else 0

        return Response(data)

class TelemetryHistorianViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Telemetriya tarixi — director va ishlab chiqarish ko'radi.
    """
    queryset = TelemetryHistorian.objects.all()
    serializer_class = TelemetryHistorianSerializer

    def get_permissions(self):
        return [IsAdminOrDirector() | IsProductionRelated()]

    def get_queryset(self):
        queryset = TelemetryHistorian.objects.all()
        tag_key = self.request.query_params.get('tag_key')
        if tag_key:
            queryset = queryset.filter(tag__key=tag_key)

        limit = self.request.query_params.get('limit')
        if limit:
            try:
                queryset = queryset[:int(limit)]
            except ValueError:
                pass
        return queryset
