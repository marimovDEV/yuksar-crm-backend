from rest_framework import serializers
from .models import PLCDevice, PLCTag, TelemetryHistorian

class PLCTagSerializer(serializers.ModelSerializer):
    class Meta:
        model = PLCTag
        fields = '__all__'

class PLCDeviceSerializer(serializers.ModelSerializer):
    tags = PLCTagSerializer(many=True, read_only=True)
    
    class Meta:
        model = PLCDevice
        fields = '__all__'

class TelemetryHistorianSerializer(serializers.ModelSerializer):
    tag_key = serializers.ReadOnlyField(source='tag.key')
    
    class Meta:
        model = TelemetryHistorian
        fields = ('id', 'tag', 'tag_key', 'value', 'timestamp')
