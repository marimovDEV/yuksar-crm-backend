from django.db import models
from django.conf import settings

class Transaction(models.Model):
    TYPE_CHOICES = (
        ('IN', 'In'),
        ('OUT', 'Out'),
        ('TRANSFER', 'Transfer'),
        ('PRODUCTION', 'Production'),
        ('SALE', 'Sale'),
        ('WASTE', 'Waste'),
    )

    product = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    block = models.ForeignKey('production_v2.FinishedBlock', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    from_warehouse = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, related_name='from_wh')
    to_warehouse = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, related_name='to_wh')
    
    from_location_name = models.CharField(max_length=255, null=True, blank=True)
    to_location_name = models.CharField(max_length=255, null=True, blank=True)
    
    quantity = models.FloatField()
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    batch = models.ForeignKey('warehouse_v2.RawMaterialBatch', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    batch_number = models.CharField(max_length=100, null=True, blank=True)
    
    document = models.ForeignKey('documents.Document', on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.type}: {self.product.name} ({self.quantity}) - {self.batch_number}"
