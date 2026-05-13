"""
Compliance & Legal Models
"""

from django.db import models
from django.conf import settings

class LegalDocument(models.Model):
    class DocType(models.TextChoices):
        INVOICE = 'INVOICE', 'Faktura'
        CONTRACT = 'CONTRACT', 'Shartnoma'
        ACT = 'ACT', 'Dalolatnoma'
        TAX_REPORT = 'TAX_REPORT', 'Soliq Hisoboti'
        CERTIFICATE = 'CERTIFICATE', 'Sertifikat'
        OTHER = 'OTHER', 'Boshqa'

    class Status(models.TextChoices):
        DRAFT = 'DRAFT', 'Qoralama'
        PENDING = 'PENDING', 'Imzoga kutilmoqda'
        SIGNED = 'SIGNED', 'Imzolangan'
        ARCHIVED = 'ARCHIVED', 'Arxivlangan'

    doc_number = models.CharField(max_length=100, unique=True, help_text="Hujjat raqami")
    title = models.CharField(max_length=255)
    doc_type = models.CharField(max_length=50, choices=DocType.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    
    file = models.FileField(upload_to='compliance_docs/', null=True, blank=True)
    
    # E-Imzo / Didox kabi tizimlar uchun xesh yoki signaturkalar
    digital_signature = models.TextField(null=True, blank=True, help_text="E-imzo xeshi")
    
    signed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='signed_docs')
    signed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Yuridik Hujjat'
        verbose_name_plural = 'Yuridik Hujjatlar'

    def __str__(self):
        return f"{self.doc_number} - {self.title}"

class DocumentVersion(models.Model):
    """Hujjatlar tarixini saqlash - v1, v2, v3."""
    document = models.ForeignKey(LegalDocument, on_delete=models.CASCADE, related_name='versions')
    version_number = models.PositiveIntegerField(default=1)
    file = models.FileField(upload_to='compliance_docs/versions/')
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    change_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-version_number']
        unique_together = ('document', 'version_number')

    def __str__(self):
        return f"{self.document.doc_number} - v{self.version_number}"



class ComplianceRule(models.Model):
    """
    Kompilyans qoidalari (Biznes qoidalar).
    Masalan: Minus sklad taqiqlash, Hujjatsiz sotuv taqiqlash.
    """
    class RuleType(models.TextChoices):
        NEGATIVE_STOCK = 'NEGATIVE_STOCK', 'Minus sklad taqiqlash'
        NO_DOCUMENT = 'NO_DOCUMENT', 'Hujjatsiz operatsiya'
        TAX_LIMIT = 'TAX_LIMIT', 'Soliq chegarasi buzilishi'

    class Severity(models.TextChoices):
        WARNING = 'WARNING', 'Ogohlantirish'
        BLOCK = 'BLOCK', 'Bloklash'

    name = models.CharField(max_length=200)
    rule_type = models.CharField(max_length=50, choices=RuleType.choices, unique=True)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.BLOCK)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name


class ComplianceViolation(models.Model):
    """Qoida buzilishini qayd etuvchi jurnal."""
    rule = models.ForeignKey(ComplianceRule, on_delete=models.CASCADE)
    description = models.TextField()
    context_data = models.JSONField(null=True, blank=True, help_text="Buzilgan obyekt xususiyatlari")
    
    is_resolved = models.BooleanField(default=False)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    resolution_note = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Violation: {self.rule.name} - {self.created_at.date()}"


class AttendanceRecord(models.Model):
    STATUS_CHOICES = (
        ('PRESENT', 'Keldi'),
        ('ABSENT', 'Kelmadi'),
        ('LATE', 'Kech keldi'),
        ('HALF_DAY', 'Yarim kun'),
        ('REMOTE', 'Masofaviy'),
    )

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='attendance_records'
    )
    date = models.DateField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PRESENT')
    check_in = models.TimeField(null=True, blank=True)
    check_out = models.TimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='recorded_attendances'
    )

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['-date']

    def __str__(self):
        return f"{self.employee} — {self.date} ({self.status})"
