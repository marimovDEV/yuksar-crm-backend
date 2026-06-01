from django.db import models
from django.conf import settings

class FinishingJob(models.Model):
    STAGE_CHOICES = (
        ('ARMIRLASH', 'Armirlash (Reinforcing)'),
        ('SHPAKLYOVKA', 'Shpaklyovka (Plastering)'),
        ('DRYING', 'Quritish (Drying)'),
        ('READY', 'Tayyor (Ready for Sklad 4)'),
    )
    
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('RUNNING', 'Jarayonda'),
        ('PAUSED', 'To‘xtatilgan'),
        ('COMPLETED', 'Tugallangan'),
        ('CANCELLED', 'Bekor qilindi'),
    )

    job_number = models.CharField(max_length=50, unique=True)
    
    # Link to CNC output if applicable
    cnc_job = models.ForeignKey('cnc_v2.CNCJob', on_delete=models.SET_NULL, null=True, blank=True, related_name='finishing_jobs')
    input_finished_block = models.ForeignKey('production_v2.FinishedBlock', on_delete=models.SET_NULL, null=True, blank=True, related_name='finishing_jobs')
    
    # Link to production pipeline stage
    order_stage = models.ForeignKey('production_v2.ProductionOrderStage', on_delete=models.SET_NULL, null=True, blank=True, related_name='finishing_jobs')
    
    # Material being produced (Final Decorative Product)
    product = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    
    quantity = models.IntegerField(help_text="Planned quantity")
    finished_quantity = models.IntegerField(default=0)
    waste_quantity = models.IntegerField(default=0)
    
    total_duration_seconds = models.IntegerField(default=0)
    last_started_at = models.DateTimeField(null=True, blank=True)
    
    current_stage = models.CharField(max_length=20, choices=STAGE_CHOICES, default='ARMIRLASH')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    notes = models.TextField(blank=True, null=True)
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.job_number} - {self.product.name} ({self.current_stage})"

class FinishingStageLog(models.Model):
    job = models.ForeignKey(FinishingJob, on_delete=models.CASCADE, related_name='stage_logs')
    stage = models.CharField(max_length=20, choices=FinishingJob.STAGE_CHOICES)
    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    
    def __str__(self):
        return f"{self.job.job_number} - {self.stage}"
