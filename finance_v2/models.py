from django.db import models
from django.db import transaction
from django.conf import settings
from django.core.exceptions import ValidationError

class Cashbox(models.Model):
    TYPE_CHOICES = (
        ('CASH', 'Naqd kassa'),
        ('BANK', 'Bank hisobi (Perezichleniya)'),
        ('CARD', 'Karta (Humo/Uzcard)'),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='CASH')
    balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    min_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0, help_text="Alert trigger threshold")
    branch = models.CharField(max_length=100, default="Asosiy Filial")
    responsible_person = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='managed_cashboxes')
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.get_type_display()}) - {self.balance}"

class ExpenseCategory(models.Model):
    TYPE_CHOICES = (
        ('INCOME', 'Kirim Kategoriyasi'),
        ('EXPENSE', 'Xarajat Kategoriyasi'),
    )
    name = models.CharField(max_length=100)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='EXPENSE')
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, related_name='children')
    description = models.TextField(blank=True)

    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name

class FinancialTransaction(models.Model):
    TYPE_CHOICES = (
        ('INCOME', 'Kirim (In)'),
        ('EXPENSE', 'Chiqim (Out)'),
    )
    STATUS_CHOICES = (
        ('DRAFT', 'Qoralama'),
        ('PENDING', 'Tasdiq kutilmoqda'),
        ('APPROVED', 'Tasdiqlangan'),
        ('CANCELLED', 'Bekor qilingan'),
    )
    DEPT_CHOICES = (
        ('ADMIN', 'Administratsiya'),
        ('PRODUCTION', 'Ishlab chiqarish'),
        ('LOGISTICS', 'Logistika'),
        ('SALES', 'Sotuv'),
        ('OTHER', 'Boshqa'),
    )
    cashbox = models.ForeignKey(Cashbox, on_delete=models.CASCADE, related_name='transactions')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='APPROVED')
    
    department = models.CharField(max_length=20, choices=DEPT_CHOICES, default='OTHER')
    category = models.ForeignKey(ExpenseCategory, on_delete=models.SET_NULL, null=True, blank=True)
    
    # Sources
    customer = models.ForeignKey('sales_v2.Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='finance_history')
    source_order = models.ForeignKey('sales_v2.Invoice', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments')
    source_purchase = models.ForeignKey('warehouse_v2.PurchaseOrder', on_delete=models.SET_NULL, null=True, blank=True, related_name='expenses')
    
    description = models.TextField(blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='approved_transactions')
    
    attachment = models.FileField(upload_to='finance/attachments/', null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True, help_text="Forecasted date for payment")
    
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': "Miqdor 0 dan katta bo'lishi kerak."})

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        if not is_new:
            return super().save(*args, **kwargs)

        # Basic validation
        self.full_clean()
        
        # Approval logic: Large transactions (> 10m) default to PENDING unless admin
        if self.amount > 10000000 and self.type == 'EXPENSE' and not (self.performed_by and self.performed_by.is_superuser):
            self.status = 'PENDING'

        with transaction.atomic():
            # Balance updates ONLY if APPROVED
            if self.status == 'APPROVED':
                cashbox = Cashbox.objects.select_for_update().get(pk=self.cashbox_id)
                if self.type == 'EXPENSE' and cashbox.balance < self.amount:
                    raise ValidationError({'amount': "Kassada mablag' yetarli emas."})

                if self.type == 'INCOME':
                    cashbox.balance += self.amount
                else:
                    cashbox.balance -= self.amount
                cashbox.save(update_fields=['balance'])
                self.cashbox = cashbox

                if self.customer:
                    balance, _ = ClientBalance.objects.get_or_create(customer=self.customer)
                    balance = ClientBalance.objects.select_for_update().get(pk=balance.pk)
                    if self.type == 'INCOME':
                        balance.total_debt -= self.amount
                    else:
                        balance.total_debt += self.amount
                    balance.save(update_fields=['total_debt', 'last_updated'])

            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.type} ({self.status}): {self.amount} via {self.cashbox.name}"

class InternalTransfer(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('COMPLETED', 'Bajarildi'),
        ('CANCELLED', 'Bekor qilindi'),
    )
    from_cashbox = models.ForeignKey(Cashbox, on_delete=models.CASCADE, related_name='transfers_out')
    to_cashbox = models.ForeignKey(Cashbox, on_delete=models.CASCADE, related_name='transfers_in')
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='COMPLETED')
    description = models.TextField(blank=True)
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.amount is None or self.amount <= 0:
            raise ValidationError({'amount': "Miqdor 0 dan katta bo'lishi kerak."})
        if self.from_cashbox_id and self.to_cashbox_id and self.from_cashbox_id == self.to_cashbox_id:
            raise ValidationError("Pulni bir xil kassaning o'ziga o'tkazib bo'lmaydi.")

    def save(self, *args, **kwargs):
        if self.pk:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            self.full_clean()
            if self.status == 'COMPLETED':
                from_cashbox = Cashbox.objects.select_for_update().get(pk=self.from_cashbox_id)
                to_cashbox = Cashbox.objects.select_for_update().get(pk=self.to_cashbox_id)

                if from_cashbox.balance < self.amount:
                    raise ValidationError({'amount': "O'tkazma uchun kassada mablag' yetarli emas."})

                from_cashbox.balance -= self.amount
                to_cashbox.balance += self.amount
                from_cashbox.save(update_fields=['balance'])
                to_cashbox.save(update_fields=['balance'])

                self.from_cashbox = from_cashbox
                self.to_cashbox = to_cashbox
            
            super().save(*args, **kwargs)

class ClientBalance(models.Model):
    customer = models.OneToOneField('sales_v2.Customer', on_delete=models.CASCADE, related_name='balance')
    total_debt = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    overdue_debt = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    last_payment_date = models.DateTimeField(null=True, blank=True)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.customer.name}: {self.total_debt}"
