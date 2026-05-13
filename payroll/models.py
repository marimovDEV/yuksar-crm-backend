from django.db import models
from django.conf import settings
from django.utils import timezone


class PayrollRecord(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('PAID', "To'langan"),
        ('PARTIAL', 'Qisman'),
    )

    employee = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='payroll_records'
    )
    month = models.CharField(max_length=7, help_text='YYYY-MM format, e.g. 2026-05')

    base_salary = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bonus = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    deduction = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=15, decimal_places=2, default=0)

    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    paid_at = models.DateTimeField(null=True, blank=True)
    paid_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='payroll_payments_made'
    )

    position = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        self.total = self.base_salary + self.bonus - self.deduction
        if not self.position and self.employee_id:
            try:
                role = self.employee.role_obj
                self.position = role.name if role else self.employee.role or ''
            except Exception:
                pass
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee} — {self.month} ({self.status})"

    class Meta:
        verbose_name = 'Payroll Record'
        verbose_name_plural = 'Payroll Records'
        ordering = ['-month', 'employee__full_name']
        unique_together = ('employee', 'month')
