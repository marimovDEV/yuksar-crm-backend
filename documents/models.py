import uuid
from django.conf import settings
from django.db import models

class Document(models.Model):
    TYPE_CHOICES = (
        ('HISOB_FAKTURA_KIRIM', 'Hisob-faktura (Kirim)'),
        ('HISOB_FAKTURA_CHIQIM', 'Hisob-faktura (Chiqim)'),
        ('ICHKI_YUK_XATI', 'Ichki yuk xati'),
        ('OTKAZMA_BUYRUGI', 'O‘tkazma buyrug‘i'),
        ('PRODUCTION_ORDER', 'Ishlab chiqarish buyrug‘i'),
        ('ISSUE_ORDER', 'Berish buyrug‘i'),
        ('ZAMES_LOG', 'Zames Jurnali (Kengaytirish)'),
        ('BUNKER_ENTRY', 'Bunker Kirimi'),
        ('FORMOVKA_LOG', 'Formovka Jurnali'),
        ('STAGE_UPDATE', 'Bosqich Yangilanishi (CNC/Pardozlash)'),
    )

    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('CREATED', 'Yaratildi'),
        ('CONFIRMED', 'Tasdiqlangan'),
        ('APPROVED', 'Tasdiqlandi'),
        ('IN_PROGRESS', 'Jarayonda'),
        ('IN_TRANSIT', "Yo'lda"),
        ('DONE', 'Yakunlandi'),
        ('CANCELLED', 'Bekor qilingan'),
        ('RETURNED', 'Qaytarildi'),
    )

    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CREATED')
    number = models.CharField(max_length=50, null=True, blank=True) # Official doc number
    
    # Invoice Specifics
    invoice_date = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=255, null=True, blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default='UZS') # UZS, USD
    exchange_rate = models.FloatField(default=1.0)
    
    from_warehouse = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='outgoing_docs')
    to_warehouse = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True, related_name='incoming_docs')
    client = models.ForeignKey('sales_v2.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    supplier = models.ForeignKey('warehouse_v2.Supplier', on_delete=models.SET_NULL, null=True, blank=True, related_name='documents')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    deadline = models.DateTimeField(null=True, blank=True)
    qr_code = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.number:
            prefix = 'DOC'
            if self.type == 'HISOB_FAKTURA_KIRIM': prefix = 'INV-IN'
            elif self.type == 'HISOB_FAKTURA_CHIQIM': prefix = 'INV-OUT'
            elif self.type == 'ICHKI_YUK_XATI': prefix = 'INT'
            elif self.type == 'OTKAZMA_BUYRUGI': prefix = 'TRF'
            
            from datetime import datetime
            now = datetime.now()
            count = Document.objects.filter(type=self.type, created_at__year=now.year, created_at__month=now.month).count() + 1
            self.number = f"{prefix}-{now.year}-{now.month:02d}-{count:04d}"
        super().save(*args, **kwargs)

    @property
    def from_entity_name(self) -> str:
        if self.from_warehouse:
            return self.from_warehouse.name
        if self.supplier_name:
            return self.supplier_name
        return "Noma'lum"

    @property
    def to_entity_name(self) -> str:
        if self.to_warehouse:
            return self.to_warehouse.name
        if self.client:
            return self.client.name
        return "Noma'lum"

    @property
    def qr_content(self):
        """Structured QR data for Industrial ERP Scanning"""
        return f"DOC:{self.number}"

    def __str__(self):
        return f"{self.number} ({self.get_type_display()})"

class DocumentItem(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    quantity = models.FloatField()
    price_at_moment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    batch_number = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return f"{self.product.name} ({self.batch_number}) x {self.quantity}"

class PrintRecord(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='print_logs')
    printed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    printed_at = models.DateTimeField(auto_now_add=True)
    copies = models.PositiveIntegerField(default=1)
    
    def __str__(self):
        return f"Print of {self.document.number} by {self.printed_by}"

class DocumentDelivery(models.Model):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name='delivery')
    courier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='doc_deliveries')
    pickup_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    recipient_signature_qr = models.TextField(blank=True) # Data from QR confirmation
    
    @property
    def qr_content(self):
        """Structured QR data for Industrial ERP Scanning"""
        return f"DOC:{self.document.number}"

    def __str__(self):
        return f"Delivery for {self.document.number}"
