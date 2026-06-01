from django.db import models
from django.conf import settings

class CNCJob(models.Model):
    STATUS_CHOICES = (
        ('CREATED', 'Yaratildi'),
        ('RUNNING', 'Jarayonda'),
        ('PAUSED', 'To‘xtatilgan'),
        ('COMPLETED', 'Tugallangan'),
        ('CANCELLED', 'Bekor qilindi'),
    )
    
    job_number = models.CharField(max_length=50, unique=True)
    # Master Production Batch
    production_batch = models.ForeignKey('production_v2.ProductionBatch', on_delete=models.CASCADE, related_name='cnc_jobs', null=True, blank=True)
    # Link to production stage if part of an overall order
    order_stage = models.OneToOneField('production_v2.ProductionOrderStage', on_delete=models.CASCADE, related_name='cnc_job', null=True, blank=True)
    
    # Input/Output Transformation
    input_block = models.ForeignKey('production_v2.BlockProduction', on_delete=models.CASCADE, related_name='cnc_jobs', null=True, blank=True)
    input_finished_block = models.ForeignKey('production_v2.FinishedBlock', on_delete=models.SET_NULL, null=True, blank=True, related_name='cnc_jobs')
    output_product = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    
    quantity_planned = models.IntegerField()
    quantity_finished = models.IntegerField(default=0)
    
    waste_m3 = models.FloatField(default=0, help_text="Volume of waste in m3")
    machine_id = models.CharField(max_length=50, choices=(('CNC-1', 'CNC #1'), ('CNC-2', 'CNC #2')))
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='CREATED')
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    priority = models.IntegerField(default=1) # 1: Normal, 2: High, 3: Urgent
    
    total_duration_seconds = models.IntegerField(default=0, help_text="Cumulative work time in seconds")
    last_started_at = models.DateTimeField(null=True, blank=True)
    
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.job_number} - {self.output_product.name}"

class WasteProcessing(models.Model):
    STATUS_CHOICES = (
        ('RAW', 'Xom-ashyo (Chiqindi)'),
        ('RECYCLED', 'Qayta ishlangan'),
    )
    
    DEPT_CHOICES = (
        ('CNC', 'CNC Sexi'),
        ('BLOCK', 'Blok Kesish'),
        ('COATING', 'Armirlash (Coating)'),
        ('PACKAGING', 'Qadoqlash'),
        ('OTHER', 'Boshqa'),
    )
    
    REASON_CHOICES = (
        ('CUTTING', 'Kesish chiqindisi'),
        ('DEFECT', 'Brak (Sifat nazoratidan o‘tmadi)'),
        ('TRANSPORT', 'Transportdagi zarar'),
        ('STORAGE', 'Saqlashdagi yo‘qotish'),
        ('OTHER', 'Boshqa sabab'),
    )

    job = models.ForeignKey(CNCJob, on_delete=models.SET_NULL, null=True, blank=True, related_name='wastes')
    batch_number = models.CharField(max_length=100, blank=True, null=True, help_text="Partiya raqami (agar CNC job bo'lmasa)")
    
    source_department = models.CharField(max_length=30, choices=DEPT_CHOICES, default='OTHER')
    reason = models.CharField(max_length=30, choices=REASON_CHOICES, default='CUTTING')
    
    waste_amount_kg = models.FloatField(help_text="Amount in kg")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='RAW')
    
    notes = models.TextField(blank=True, null=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='waste_processing')
    date = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Waste {self.waste_amount_kg}kg - {self.status} ({self.date.strftime('%Y-%m-%d')})"
