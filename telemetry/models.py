from django.db import models

class PLCDevice(models.Model):
    name = models.CharField(max_length=100) # e.g., Prefoamer PV-1, Molder BF-12
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    port = models.IntegerField(default=502) # Default Modbus TCP port
    protocol = models.CharField(max_length=20, choices=(
        ('MODBUS', 'Modbus TCP'),
        ('OPCUA', 'OPC UA'),
        ('SIMULATOR', 'Sanoat Simulyatori'),
    ), default='SIMULATOR')
    is_connected = models.BooleanField(default=True)
    last_ping = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.protocol})"

class PLCTag(models.Model):
    device = models.ForeignKey(PLCDevice, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=100) # e.g., Bug' bosimi, Kamera harorati
    key = models.CharField(max_length=100, unique=True) # e.g., pv1_steam_pressure, pv1_chamber_temp
    address = models.CharField(max_length=50, blank=True) # e.g., HR_40001, node-id
    data_type = models.CharField(max_length=20, choices=(
        ('FLOAT', 'Float'),
        ('INT', 'Integer'),
        ('BOOL', 'Boolean'),
    ), default='FLOAT')
    current_value = models.FloatField(default=0.0)
    unit = models.CharField(max_length=20, blank=True) # e.g., bar, °C, kg/m³
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.device.name} -> {self.name}: {self.current_value} {self.unit}"

class TelemetryHistorian(models.Model):
    tag = models.ForeignKey(PLCTag, on_delete=models.CASCADE, related_name='history')
    value = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['tag', 'timestamp']),
        ]

    def __str__(self):
        return f"{self.tag.key} -> {self.value} at {self.timestamp}"
