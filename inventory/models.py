import uuid
from django.db import models
from django.conf import settings

class ProductSource(models.TextChoices):
    INTERNAL = 'INTERNAL', 'O\'z mahsulotimiz (Produksiya)'
    EXTERNAL = 'EXTERNAL', 'Tashqaridan kelgan mahsulot'

class InventoryBatch(models.Model):
    STATUS_CHOICES = (
        ('IN_STOCK', 'Omborda'),
        ('RESERVED', 'Band qilingan'),
        ('DEPLETED', 'Tugatilgan'),
        ('PROJECT_USE', 'Loyiha uchun sarflangan'),
        ('WASTE', 'Chiqindi'),
    )
    
    batch_number = models.CharField(max_length=100, unique=True)
    product = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE, related_name='inventory_batches')
    source = models.CharField(max_length=20, choices=ProductSource.choices, default=ProductSource.EXTERNAL)
    
    initial_weight = models.DecimalField(max_digits=15, decimal_places=3, help_text="Starting weight in grams/kg")
    current_weight = models.DecimalField(max_digits=15, decimal_places=3, help_text="Current available weight")
    reserved_weight = models.DecimalField(max_digits=15, decimal_places=3, default=0, help_text="Reserved weight for orders")
    
    location = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_STOCK')
    
    qr_id = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Soft deletion field
    is_deleted = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.batch_number} | {self.product.name} | {self.current_weight} {self.product.unit}"

    @property
    def quantity(self):
        return self.current_weight

    @quantity.setter
    def quantity(self, value):
        self.current_weight = value

    @property
    def reserved_quantity(self):
        return self.reserved_weight

    @property
    def warehouse(self):
        return self.location

    @warehouse.setter
    def warehouse(self, value):
        self.location = value

    @reserved_quantity.setter
    def reserved_quantity(self, value):
        self.reserved_weight = value

class InventoryQuerySet(models.QuerySet):
    def _translate_kwargs(self, kwargs):
        if 'quantity' in kwargs:
            kwargs['current_weight'] = kwargs.pop('quantity')
        if 'reserved_quantity' in kwargs:
            kwargs['reserved_weight'] = kwargs.pop('reserved_quantity')
        if 'warehouse' in kwargs:
            kwargs['location'] = kwargs.pop('warehouse')
        return kwargs

    def filter(self, *args, **kwargs):
        return super().filter(*args, **self._translate_kwargs(kwargs))

    def get(self, *args, **kwargs):
        return super().get(*args, **self._translate_kwargs(kwargs))

    def create(self, **kwargs):
        qty = kwargs.get('quantity')
        if qty is not None:
            kwargs.setdefault('initial_weight', qty)
        return super().create(**self._translate_kwargs(kwargs))

    def get_or_create(self, defaults=None, **kwargs):
        if defaults:
            defaults = self._translate_kwargs(dict(defaults))
        qty = kwargs.get('quantity')
        if qty is not None:
            kwargs.setdefault('initial_weight', qty)
        return super().get_or_create(defaults=defaults, **self._translate_kwargs(kwargs))

class Inventory(InventoryBatch):
    objects = InventoryQuerySet.as_manager()

    class Meta:
        proxy = True

    def __init__(self, *args, **kwargs):
        quantity = kwargs.pop('quantity', None)
        reserved_quantity = kwargs.pop('reserved_quantity', None)
        warehouse = kwargs.pop('warehouse', None)
        
        super().__init__(*args, **kwargs)
        
        if quantity is not None:
            self.current_weight = quantity
            if not self.initial_weight:
                self.initial_weight = quantity
        if reserved_quantity is not None:
            self.reserved_weight = reserved_quantity
        if warehouse is not None:
            self.location = warehouse

class InventoryMovement(models.Model):
    TYPE_CHOICES = (
        ('IN', 'Kirim (In)'),
        ('OUT', 'Chiqim (Out)'),
        ('TRANSFER', 'Ko\'chirish (Transfer)'),
        ('ADJUSTMENT', 'Tuzatish (Adjustment)'),
    )
    
    batch = models.ForeignKey(InventoryBatch, on_delete=models.CASCADE, related_name='movements')
    from_location = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='movements_out')
    to_location = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='movements_in')
    
    quantity = models.DecimalField(max_digits=15, decimal_places=3)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    
    reference = models.CharField(max_length=100, blank=True, help_text="e.g., Zames-101, Sale-501, Project-X")
    timestamp = models.DateTimeField(auto_now_add=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.type} | {self.quantity} | Batch: {self.batch.batch_number}"
