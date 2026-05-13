from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Driver, TransportContract, Waybill, Trip, DriverPayment, FuelLog, Vehicle
from .serializers import (
    DriverSerializer, TransportContractSerializer, WaybillSerializer,
    TripSerializer, DriverPaymentSerializer, FuelLogSerializer, VehicleSerializer
)
from .services import start_trip, complete_trip

class DriverViewSet(viewsets.ModelViewSet):
    queryset = Driver.objects.all()
    serializer_class = DriverSerializer

class TransportContractViewSet(viewsets.ModelViewSet):
    queryset = TransportContract.objects.all()
    serializer_class = TransportContractSerializer

class WaybillViewSet(viewsets.ModelViewSet):
    queryset = Waybill.objects.all().order_by('-date', '-created_at')
    serializer_class = WaybillSerializer

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        trip = start_trip(pk, user=request.user)
        return Response(TripSerializer(trip).data)

class TripViewSet(viewsets.ModelViewSet):
    queryset = Trip.objects.all().order_by('-start_time')
    serializer_class = TripSerializer

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        actual_distance = request.data.get('actual_distance')
        if actual_distance is None:
            return Response({"error": "actual_distance is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        trip = complete_trip(pk, actual_distance=actual_distance, user=request.user)
        return Response(self.get_serializer(trip).data)

class DriverPaymentViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = DriverPayment.objects.all().order_by('-created_at')
    serializer_class = DriverPaymentSerializer

class FuelLogViewSet(viewsets.ModelViewSet):
    queryset = FuelLog.objects.all()
    serializer_class = FuelLogSerializer


class VehicleViewSet(viewsets.ModelViewSet):
    queryset = Vehicle.objects.all().order_by('-created_at')
    serializer_class = VehicleSerializer
