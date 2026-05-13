from rest_framework import serializers
from .models import Driver, TransportContract, Waybill, Trip, DriverPayment, FuelLog, Vehicle

class DriverSerializer(serializers.ModelSerializer):
    class Meta:
        model = Driver
        fields = '__all__'

class TransportContractSerializer(serializers.ModelSerializer):
    driver_name = serializers.ReadOnlyField(source='driver.full_name')
    
    class Meta:
        model = TransportContract
        fields = '__all__'

class WaybillSerializer(serializers.ModelSerializer):
    driver_name = serializers.ReadOnlyField(source='driver.full_name')
    vehicle_number = serializers.ReadOnlyField(source='driver.vehicle_number')
    dispatcher_name = serializers.ReadOnlyField(source='dispatcher.username')
    
    class Meta:
        model = Waybill
        fields = '__all__'

class TripSerializer(serializers.ModelSerializer):
    waybill_details = WaybillSerializer(source='waybill', read_only=True)
    
    class Meta:
        model = Trip
        fields = '__all__'

class DriverPaymentSerializer(serializers.ModelSerializer):
    driver_name = serializers.ReadOnlyField(source='driver.full_name')
    trip_id = serializers.ReadOnlyField(source='trip.id')
    
    class Meta:
        model = DriverPayment
        fields = '__all__'

class FuelLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = FuelLog
        fields = '__all__'


class VehicleSerializer(serializers.ModelSerializer):
    driver_name = serializers.ReadOnlyField(source='driver.full_name')

    class Meta:
        model = Vehicle
        fields = '__all__'
