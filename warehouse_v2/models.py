import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone

class Supplier(models.Model):
    STATUS_CHOICES = (
        ('ACTIVE', 'Aktiv'),
        ('BLOCKED', 'Bloklangan'),
        ('INACTIVE', 'Noaktiv'),
    )
    name = models.CharField(max_length=255)
    inn = models.CharField(max_length=20, null=True, blank=True, verbose_name="INN/STIR")
    contact_info = models.TextField(blank=True)
    manager_name = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(blank=True)
    material_type = models.CharField(max_length=255, null=True, blank=True, help_text="e.g., EPS Granula, Gaz, Chemical")
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=5.0)
    total_debt = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    
    # Contract details
    contract_number = models.CharField(max_length=100, null=True, blank=True)
    contract_expiry = models.DateField(null=True, blank=True)
    
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name

class PurchaseOrder(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Qoralama'
        PENDING = 'PENDING', 'Tasdiqlash kutilmoqda'
        APPROVED = 'APPROVED', 'Tasdiqlandi'
        ORDERED = 'ORDERED', 'Buyurtma berildi'
        IN_TRANSIT = 'IN_TRANSIT', 'Yo\'lda'
        RECEIVED = 'RECEIVED', 'Qabul qilindi'
        CANCELLED = 'CANCELLED', 'Bekor qilindi'

    po_number = models.CharField(max_length=50, unique=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='purchase_orders')
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    total_amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=20, default='UZS')
    
    expected_delivery = models.DateField(null=True, blank=True, verbose_name="ETA")
    received_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.po_number:
            last = PurchaseOrder.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.po_number = f"PO-{num:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.po_number} - {self.supplier.name}"

class PurchaseOrderItem(models.Model):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    price_per_unit = models.DecimalField(max_digits=18, decimal_places=2)
    total_price = models.DecimalField(max_digits=18, decimal_places=2)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.price_per_unit
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.order.po_number}: {self.material.name} x {self.quantity}"

class Material(models.Model):
    # Shared material/product model
    CATEGORY_CHOICES = (
        ('RAW', 'Xom-ashyo'),
        ('SEMI', 'Yarim tayyor mahsulot'),
        ('FINISHED', 'Tayyor mahsulot'),
        ('OTHER', 'Boshqa'),
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=50, unique=True, null=True, blank=True)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES, default='OTHER')
    unit = models.CharField(max_length=20, default='kg')
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True, null=True)
    
    def __str__(self):
        return self.name

class RawMaterialBatch(models.Model):
    STATUS_CHOICES = (
        ('RECEIVED', 'Qabul qilindi'),
        ('INSPECTION', 'Tekshiruvda'),
        ('IN_STOCK', 'Omborda'),
        ('RESERVED', 'Band qilingan'),
        ('DEPLETED', 'Tugatilgan'),
        ('CANCELLED', 'Bekor qilindi'),
    )
    invoice_number = models.CharField(max_length=100)
    supplier_name = models.CharField(max_length=255, null=True, blank=True)
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name='batches', null=True, blank=True)
    date = models.DateField(auto_now_add=True)
    expiry_date = models.DateField(null=True, blank=True)
    quantity_kg = models.DecimalField(max_digits=18, decimal_places=3)
    remaining_quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    reserved_quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    batch_number = models.CharField(max_length=100, unique=True)
    price_per_unit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    currency = models.CharField(max_length=20, default='UZS')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='IN_STOCK')
    qr_code = models.UUIDField(default=uuid.uuid4, editable=False)
    responsible_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    material = models.ForeignKey(Material, on_delete=models.CASCADE, null=True)

    @property
    def qr_content(self):
        """Structured QR data for Industrial ERP Scanning"""
        return f"BAT:{self.batch_number}"

    def __str__(self):
        return f"Batch {self.batch_number} - {self.material.name}"

class Warehouse(models.Model):
    name = models.CharField(max_length=100) # Sklad 1, 2, 3, 4
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

class Stock(models.Model):
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='stocks')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    min_level = models.DecimalField(max_digits=18, decimal_places=3, default=0, help_text="Ogohlantirish darajasi")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('warehouse', 'material')

    def __str__(self):
        return f"{self.warehouse.name}: {self.material.name} ({self.quantity})"

class WarehouseTransfer(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Qoralama'
        PENDING = 'PENDING', 'Tasdiqlash kutilmoqda'
        APPROVED = 'APPROVED', 'Tasdiqlandi'
        IN_TRANSIT = 'IN_TRANSIT', 'Yo‘lda'
        SHIPPED = 'SHIPPED', 'Yo‘lda (Eski holat)'
        RECEIVED = 'RECEIVED', 'Qabul qilindi'
        COMPLETED = 'COMPLETED', 'Yakunlandi'
        CANCELLED = 'CANCELLED', 'Bekor qilindi'

    class TransferType(models.TextChoices):
        PRODUCTION = 'PRODUCTION', 'Ishlab chiqarish uchun'
        WAREHOUSE = 'WAREHOUSE', 'Omborlararo'
        QC = 'QC', 'Sifat nazorati (QC)'
        RETURN = 'RETURN', 'Qaytarish'
        WASTE = 'WASTE', 'Brak / Chiqindi'

    class Priority(models.TextChoices):
        LOW = 'LOW', 'Past'
        NORMAL = 'NORMAL', 'O‘rtacha'
        HIGH = 'HIGH', 'Yuqori'
        URGENT = 'URGENT', 'SHOSHILINCH'

    transfer_number = models.CharField(max_length=50, unique=True, blank=True)
    transfer_type = models.CharField(max_length=20, choices=TransferType.choices, default=TransferType.WAREHOUSE)
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.NORMAL)
    
    from_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='outgoing_transfers')
    to_warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, related_name='incoming_transfers')
    
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    block = models.ForeignKey('production_v2.FinishedBlock', on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers')
    batch = models.ForeignKey(RawMaterialBatch, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers')
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    reason = models.TextField(blank=True, help_text="O'tkazma sababi")
    notes = models.TextField(blank=True)

    # Operator Tracking
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='transfers_created')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers_approved')
    shipped_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers_shipped')
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='transfers_received')

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    shipped_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    
    # Attachments can be handled by a generic model or specific fields
    attachment = models.FileField(upload_to='transfers/attachments/', null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.transfer_number:
            last = WarehouseTransfer.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.transfer_number = f"WT-{num:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.transfer_number}: {self.from_warehouse} -> {self.to_warehouse} ({self.status})"

class BatchReservation(models.Model):
    document = models.ForeignKey('documents.Document', on_delete=models.CASCADE, related_name='reservations')
    batch = models.ForeignKey(RawMaterialBatch, on_delete=models.CASCADE, related_name='reservations')
    quantity = models.DecimalField(max_digits=18, decimal_places=3)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Reservation: {self.quantity} from {self.batch.batch_number} for {self.document.number}"

# ═══════════════════════════════════════════════════
# PHASE 3: INVENTORY RECONCILIATION
# ═══════════════════════════════════════════════════

class InventoryAudit(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Qoralama'
        IN_PROGRESS = 'IN_PROGRESS', 'Sanalyapti'
        REVIEW = 'REVIEW', 'Tasdiqlash kutilmoqda'
        COMPLETED = 'COMPLETED', 'Yakunlangan'
    
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    auditor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='audits_conducted')
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='audits_approved')
    remarks = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Sklad Auditi'
        verbose_name_plural = 'Sklad Auditlari'

    def __str__(self):
        return f"Audit: {self.warehouse.name} - {self.date}"

class InventoryAuditLine(models.Model):
    audit = models.ForeignKey(InventoryAudit, on_delete=models.CASCADE, related_name='lines')
    material = models.ForeignKey(Material, on_delete=models.CASCADE)
    system_qty = models.DecimalField(max_digits=18, decimal_places=3, help_text="Tizimdagi qoldiq")
    actual_qty = models.DecimalField(max_digits=18, decimal_places=3, help_text="Haqiqiy sanalgan qoldiq", null=True, blank=True)
    
    @property
    def variance(self):
        if self.actual_qty is None:
            return 0
        return self.actual_qty - self.system_qty

    def __str__(self):
        return f"{self.material.name}: Sys {self.system_qty} vs Act {self.actual_qty}"
