from django.db import models


class PricingRule(models.Model):
    CONDITION_CHOICES = (
        ('QUANTITY', 'Miqdor bo\'yicha'),
        ('CUSTOMER_TYPE', 'Mijoz turi bo\'yicha'),
        ('SEASON', 'Mavsum bo\'yicha'),
        ('REGION', 'Hudud bo\'yicha'),
        ('LOYALTY', 'Sodiqlik bo\'yicha'),
    )
    ADJUSTMENT_CHOICES = (
        ('PERCENT', 'Foiz'),
        ('FIXED', 'Qat\'iy miqdor'),
    )

    name = models.CharField(max_length=255)
    product = models.CharField(max_length=255, blank=True, help_text='Product name or ALL')
    condition_type = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='QUANTITY')
    threshold = models.DecimalField(max_digits=12, decimal_places=2, default=0,
                                    help_text='Min quantity or other threshold value')
    adjustment_type = models.CharField(max_length=10, choices=ADJUSTMENT_CHOICES, default='PERCENT')
    adjustment_value = models.DecimalField(max_digits=10, decimal_places=2, default=0,
                                           help_text='Discount/markup value')
    is_active = models.BooleanField(default=True)

    priority = models.IntegerField(default=0)
    valid_from = models.DateField(null=True, blank=True)
    valid_until = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.condition_type})"

    class Meta:
        verbose_name = 'Pricing Rule'
        verbose_name_plural = 'Pricing Rules'
        ordering = ['-priority', '-created_at']
