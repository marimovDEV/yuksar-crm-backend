from django.db import models
from django.conf import settings


class Dealer(models.Model):
    CATEGORY_CHOICES = (
        ('A', 'A — Premium'),
        ('B', 'B — Standart'),
        ('C', 'C — Minimal'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Faol'),
        ('INACTIVE', 'Nofaol'),
    )
    REGION_CHOICES = (
        ('Samarqand', 'Samarqand'),
        ('Namangan', 'Namangan'),
        ('Buxoro', 'Buxoro'),
        ("Farg'ona", "Farg'ona"),
        ('Toshkent', 'Toshkent'),
        ('Andijon', 'Andijon'),
        ('Xorazm', 'Xorazm'),
        ('Boshqa', 'Boshqa'),
    )

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50)
    region = models.CharField(max_length=100, choices=REGION_CHOICES, default='Toshkent')
    address = models.TextField(blank=True)
    stir = models.CharField(max_length=20, blank=True, null=True, verbose_name='STIR')

    category = models.CharField(max_length=1, choices=CATEGORY_CHOICES, default='B')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')

    credit_limit = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    debt = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    monthly_target = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    monthly_actual = models.DecimalField(max_digits=18, decimal_places=2, default=0)

    assigned_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='managed_dealers'
    )

    last_order = models.DateTimeField(null=True, blank=True)
    contract_start = models.DateField(null=True, blank=True)
    contract_end = models.DateField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.category})"

    class Meta:
        verbose_name = 'Dealer'
        verbose_name_plural = 'Dealers'
        ordering = ['-created_at']


class DealerPayment(models.Model):
    METHOD_CHOICES = (
        ('BANK', 'Bank'),
        ('CASH', 'Naqd'),
        ('CARD', 'Karta'),
    )

    dealer = models.ForeignKey(Dealer, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    method = models.CharField(max_length=10, choices=METHOD_CHOICES, default='BANK')
    note = models.TextField(blank=True)
    date = models.DateField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )

    def __str__(self):
        return f"{self.dealer.name} — {self.amount} ({self.method})"

    class Meta:
        ordering = ['-date']


class DealerOrder(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('CONFIRMED', 'Tasdiqlangan'),
        ('SHIPPED', 'Jo\'natilgan'),
        ('COMPLETED', 'Yakunlangan'),
        ('CANCELLED', 'Bekor qilingan'),
    )

    dealer = models.ForeignKey(Dealer, on_delete=models.CASCADE, related_name='orders')
    product = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True
    )

    def __str__(self):
        return f"{self.dealer.name} — {self.product} x{self.quantity}"

    class Meta:
        ordering = ['-created_at']
