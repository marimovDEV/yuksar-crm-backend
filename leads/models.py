from django.db import models
from django.conf import settings


class Lead(models.Model):
    STATUS_CHOICES = (
        ('NEW', 'Yangi'),
        ('CONTACTED', 'Bog\'lanildi'),
        ('NEGOTIATION', 'Muzokara'),
        ('WON', 'Yutildi'),
        ('LOST', 'Yutqazildi'),
    )
    SOURCE_CHOICES = (
        ('REFERRAL', 'Tavsiya'),
        ('WEBSITE', 'Veb-sayt'),
        ('COLD_CALL', 'Sovuq qo\'ng\'iroq'),
        ('EXHIBITION', 'Ko\'rgazma'),
        ('SOCIAL', 'Ijtimoiy tarmoq'),
        ('OTHER', 'Boshqa'),
    )

    name = models.CharField(max_length=255)
    company = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50)
    email = models.EmailField(blank=True)
    region = models.CharField(max_length=100, blank=True)

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='OTHER')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='NEW')

    amount_expected = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    notes = models.TextField(blank=True)

    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='assigned_leads'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='created_leads'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} — {self.status}"

    class Meta:
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        ordering = ['-created_at']


class LeadActivity(models.Model):
    TYPE_CHOICES = (
        ('CALL', 'Qo\'ng\'iroq'),
        ('EMAIL', 'Email'),
        ('MEETING', 'Uchrashuv'),
        ('NOTE', 'Izoh'),
    )

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='NOTE')
    note = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
