"""
Accounting Models — Double-Entry Bookkeeping System
O'zbekiston BHM (Buxgalteriya Hisobi Milliy Standarti) asosida

Key entities:
  - Account (Hisoblar rejasi / Chart of Accounts)
  - JournalEntry (Buxgalteriya yozuvi / provodka)
  - JournalEntryLine (Debit/Credit qator)
  - FiscalPeriod (Hisobot davri)
  - TaxRate (Soliq stavkalari, QQS va boshq.)
"""

import uuid
from django.db import models
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone


class AccountType(models.TextChoices):
    """
    O'zbekiston BHM kategoriyalari.
    Milliy standart bo'yicha hisoblar sinflari.
    """
    ASSET = 'ASSET', 'Aktivlar'
    LIABILITY = 'LIABILITY', 'Majburiyatlar'
    EQUITY = 'EQUITY', 'Kapital va zaxiralar'
    REVENUE = 'REVENUE', 'Daromadlar'
    EXPENSE = 'EXPENSE', 'Xarajatlar'
    CONTRA = 'CONTRA', 'Kontrar hisob'


class Account(models.Model):
    """
    Hisoblar rejasi — O'zbekiston BHM standarti.

    Standart raqamlash:
      0100-0999: Asosiy vositalar va boshqa uzoq muddatli aktivlar
      1000-1999: Ishlab chiqarish zahiralari
      2000-2999: Asosiy ishlab chiqarish xarajatlari
      3000-3999: Tayyor mahsulot va tovarlar
      4000-4999: Pul mablag'lari
      5000-5999: Hisob-kitoblar
      6000-6999: Kapital va zaxiralar
      7000-7999: Uzoq muddatli majburiyatlar
      9000-9199: Daromadlar
      9200-9499: Xarajatlar
      9500-9999: Moliyaviy natijalar
    """
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Hisob kodi (masalan: 5010, 9010)"
    )
    name = models.CharField(max_length=255, help_text="Hisob nomi")
    account_type = models.CharField(
        max_length=20,
        choices=AccountType.choices,
        help_text="Hisob turi"
    )
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text="Ota hisob (sub-account uchun)"
    )
    description = models.TextField(blank=True, help_text="Hisob tavsifi")
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(
        default=False,
        help_text="System hisobi — o'chirish mumkin emas"
    )
    balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Hisob qoldig'i (cached, recalculated)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['code']
        verbose_name = 'Hisob'
        verbose_name_plural = 'Hisoblar rejasi'

    def __str__(self):
        return f"{self.code} — {self.name}"

    @property
    def full_path(self):
        """Return full account path, e.g. '5000 > 5010 > 5011'"""
        parts = [self.code]
        parent = self.parent
        while parent:
            parts.insert(0, parent.code)
            parent = parent.parent
        return ' > '.join(parts)

    def recalculate_balance(self):
        """
        Hisob balansini JournalEntryLine'lardan qayta hisoblash.
        ASSET, EXPENSE: debit increases, credit decreases
        LIABILITY, EQUITY, REVENUE: credit increases, debit decreases
        """
        from django.db.models import Sum
        lines = JournalEntryLine.objects.filter(
            account=self,
            journal_entry__status='POSTED'
        )
        totals = lines.aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )
        total_debit = totals['total_debit'] or 0
        total_credit = totals['total_credit'] or 0

        if self.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
            self.balance = total_debit - total_credit
        else:
            self.balance = total_credit - total_debit
        self.save(update_fields=['balance', 'updated_at'])


class FiscalPeriod(models.Model):
    """
    Hisobot davri — oylik, choraklik, yillik.
    Yopilgan davrdagi yozuvlarni tahrirlash mumkin emas.
    """
    name = models.CharField(max_length=50, help_text="Masalan: 2026 Aprel")
    start_date = models.DateField()
    end_date = models.DateField()
    is_closed = models.BooleanField(
        default=False,
        help_text="Yopilgan davr — o'zgartirish mumkin emas"
    )
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='closed_periods'
    )
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-start_date']
        verbose_name = 'Hisobot davri'
        verbose_name_plural = 'Hisobot davrlari'

    def __str__(self):
        status = '🔒' if self.is_closed else '🔓'
        return f"{status} {self.name} ({self.start_date} — {self.end_date})"

    def clean(self):
        if self.start_date and self.end_date and self.start_date >= self.end_date:
            raise ValidationError("Boshlanish sanasi tugash sanasidan oldin bo'lishi kerak.")

    def close(self, user):
        """
        Davrni yopish - FINAL ENTERPRISE HARDENING.
        Qat'iy qoidalar tekshirilgandan so'nggina davr yopiladi.
        """
        # 1. Check for pending drafts
        unposted_entries = self.entries.exclude(status='POSTED').count()
        if unposted_entries > 0:
            raise ValidationError(f"Davrni yopish mumkin emas. {unposted_entries} ta tasdiqlanmagan provodka mavjud.")
            
        # 2. Check for unbalanced entries overall in period (double safety)
        for entry in self.entries.filter(status='POSTED'):
            if not entry.is_balanced:
                raise ValidationError(f"Balanslanmagan provodka topildi: {entry.entry_number}")
                
        # 3. Lock
        self.is_closed = True
        self.closed_by = user
        self.closed_at = timezone.now()
        self.save(update_fields=['is_closed', 'closed_by', 'closed_at'])


class TaxRate(models.Model):
    """
    Soliq stavkalari — QQS va boshqalar.
    SuperAdmin tomonidan sozlanadi.
    """
    name = models.CharField(max_length=100, help_text="Masalan: QQS 12%")
    code = models.CharField(
        max_length=20,
        unique=True,
        help_text="Ichki kod: VAT_12, VAT_0, EXEMPT"
    )
    rate = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Soliq foizi (masalan: 12.00)"
    )
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Soliq stavkasi'
        verbose_name_plural = 'Soliq stavkalari'

    def __str__(self):
        return f"{self.name} ({self.rate}%)"


class JournalEntry(models.Model):
    """
    Buxgalteriya yozuvi (provodka).
    Har bir operatsiya uchun bitta JournalEntry,
    ichida kamida 2 ta JournalEntryLine (debit + credit).

    Sum(debit) MUST == Sum(credit)
    """
    class EntryStatus(models.TextChoices):
        DRAFT = 'DRAFT', 'Qoralama'
        POSTED = 'POSTED', 'Tasdiqlangan'
        VOID = 'VOID', 'Bekor qilingan'

    class SourceType(models.TextChoices):
        MANUAL = 'MANUAL', 'Qo\'lda kiritilgan'
        WAREHOUSE = 'WAREHOUSE', 'Ombor operatsiyasi'
        PRODUCTION = 'PRODUCTION', 'Ishlab chiqarish'
        SALE = 'SALE', 'Sotuv'
        FINANCE = 'FINANCE', 'Moliya operatsiyasi'
        TRANSFER = 'TRANSFER', 'Ichki o\'tkazma'
        ADJUSTMENT = 'ADJUSTMENT', 'Tuzatish yozuvi'

    entry_number = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        help_text="Avtomatik: JE-00001"
    )
    date = models.DateField(default=timezone.now)
    description = models.TextField(help_text="Operatsiya tavsifi")
    source_type = models.CharField(
        max_length=20,
        choices=SourceType.choices,
        default=SourceType.MANUAL
    )
    source_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Manba obyekt ID (masalan: Invoice #5)"
    )
    source_description = models.CharField(
        max_length=255,
        blank=True,
        help_text="Masalan: 'Faktura INV-0042 uchun provodka'"
    )
    status = models.CharField(
        max_length=10,
        choices=EntryStatus.choices,
        default=EntryStatus.DRAFT
    )
    fiscal_period = models.ForeignKey(
        FiscalPeriod,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='entries'
    )
    reference = models.CharField(
        max_length=100,
        blank=True,
        help_text="Tashqi hujjat raqami"
    )
    tax_rate = models.ForeignKey(
        TaxRate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Qo'llaniladigan soliq stavkasi"
    )
    total_amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Umumiy summa (informational)"
    )
    attachment = models.FileField(
        upload_to='accounting/attachments/',
        null=True,
        blank=True,
        help_text="Tasdiqlovchi hujjat (PDF, rasm)"
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='journal_entries'
    )
    posted_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_entries'
    )
    void_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']
        verbose_name = 'Buxgalteriya yozuvi'
        verbose_name_plural = 'Buxgalteriya yozuvlari'

    def __str__(self):
        return f"{self.entry_number} — {self.description[:50]} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.entry_number:
            last = JournalEntry.objects.order_by('-id').first()
            num = (last.id + 1) if last else 1
            self.entry_number = f"JE-{num:05d}"
        super().save(*args, **kwargs)

    def clean(self):
        """Validate that the entry can be modified."""
        if self.pk and self.status == self.EntryStatus.VOID:
            raise ValidationError("Bekor qilingan yozuvni o'zgartirish mumkin emas.")
        if self.fiscal_period and self.fiscal_period.is_closed:
            raise ValidationError(
                f"Yopilgan davr ({self.fiscal_period.name}) dagi yozuvni o'zgartirish mumkin emas."
            )

    @property
    def is_balanced(self):
        """Check if total debits == total credits."""
        from django.db.models import Sum
        totals = self.lines.aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit')
        )
        debit = totals['total_debit'] or 0
        credit = totals['total_credit'] or 0
        return abs(debit - credit) < 0.01  # floating point tolerance

    @property
    def total_debit(self):
        from django.db.models import Sum
        return self.lines.aggregate(s=Sum('debit'))['s'] or 0

    @property
    def total_credit(self):
        from django.db.models import Sum
        return self.lines.aggregate(s=Sum('credit'))['s'] or 0


class JournalEntryLine(models.Model):
    """
    Debit/Credit qator — har bir provodkaning tarkibiy qismi.
    Qoida: bitta line'da faqat debit YOKI credit bo'ladi (ikkalasi emas).
    """
    journal_entry = models.ForeignKey(
        JournalEntry,
        on_delete=models.CASCADE,
        related_name='lines'
    )
    account = models.ForeignKey(
        Account,
        on_delete=models.PROTECT,
        related_name='entry_lines'
    )
    debit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Debit summasi"
    )
    credit = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        help_text="Kredit summasi"
    )
    description = models.CharField(
        max_length=500,
        blank=True,
        help_text="Qator tavsifi"
    )

    class Meta:
        verbose_name = 'Provodka qatori'
        verbose_name_plural = 'Provodka qatorlari'

    def __str__(self):
        if self.debit > 0:
            return f"DR {self.account.code}: {self.debit}"
        return f"CR {self.account.code}: {self.credit}"

    def clean(self):
        if self.debit < 0 or self.credit < 0:
            raise ValidationError("Debit va credit manfiy bo'lishi mumkin emas.")
        if self.debit > 0 and self.credit > 0:
            raise ValidationError("Bitta qatorda debit va credit bir vaqtda bo'lishi mumkin emas.")
        if self.debit == 0 and self.credit == 0:
            raise ValidationError("Debit yoki credit ko'rsatilishi kerak.")
