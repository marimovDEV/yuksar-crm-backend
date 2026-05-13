"""
Accounting Services — Double-Entry Bookkeeping Engine

Core business logic:
  - Journal entry creation, posting, voiding
  - Trial balance calculation
  - Balance sheet (Buxgalteriya balansi)
  - Income statement / P&L (Foyda va zarar)
  - Cash flow statement
  - VAT/QQS calculation
  - Chart of Accounts seeding (O'zbekiston BHM)
"""

from decimal import Decimal
from datetime import date, timedelta
from django.db import transaction
from django.db.models import Sum, Q, F
from django.utils import timezone
from django.core.exceptions import ValidationError

from .models import (
    Account, AccountType, JournalEntry, JournalEntryLine,
    FiscalPeriod, TaxRate,
)


# ═══════════════════════════════════════════════════
# 1. JOURNAL ENTRY OPERATIONS
# ═══════════════════════════════════════════════════

def create_journal_entry(
    description,
    lines,
    source_type='MANUAL',
    source_id=None,
    source_description='',
    reference='',
    date_value=None,
    user=None,
    auto_post=False,
    tax_rate_id=None,
    attachment=None,
):
    """
    Create a new journal entry with debit/credit lines.

    Args:
        description: Entry description
        lines: List of dicts: [{'account_code': '5010', 'debit': 100, 'credit': 0}, ...]
        source_type: MANUAL, WAREHOUSE, PRODUCTION, SALE, FINANCE, TRANSFER, ADJUSTMENT
        source_id: Related object ID
        user: User creating the entry
        auto_post: If True, automatically post the entry
        tax_rate_id: Optional TaxRate ID

    Returns:
        JournalEntry instance

    Raises:
        ValidationError if debit != credit
    """
    with transaction.atomic():
        # Calculate total amount
        total_debit = sum(Decimal(str(l.get('debit', 0))) for l in lines)
        total_credit = sum(Decimal(str(l.get('credit', 0))) for l in lines)

        if abs(total_debit - total_credit) > Decimal('0.01'):
            raise ValidationError(
                f"Debit ({total_debit}) va Credit ({total_credit}) teng emas! "
                f"Farq: {abs(total_debit - total_credit)}"
            )

        entry = JournalEntry.objects.create(
            date=date_value or timezone.now().date(),
            description=description,
            source_type=source_type,
            source_id=str(source_id) if source_id else None,
            source_description=source_description,
            reference=reference,
            total_amount=total_debit,
            created_by=user,
            tax_rate_id=tax_rate_id,
            attachment=attachment,
        )


        for line_data in lines:
            account_code = line_data.get('account_code')
            account_id = line_data.get('account_id')

            if account_code:
                try:
                    account = Account.objects.get(code=account_code, is_active=True)
                except Account.DoesNotExist:
                    raise ValidationError(f"Hisob topilmadi: {account_code}")
            elif account_id:
                try:
                    account = Account.objects.get(id=account_id, is_active=True)
                except Account.DoesNotExist:
                    raise ValidationError(f"Hisob topilmadi: ID {account_id}")
            else:
                raise ValidationError("account_code yoki account_id ko'rsatilishi kerak.")

            JournalEntryLine.objects.create(
                journal_entry=entry,
                account=account,
                debit=Decimal(str(line_data.get('debit', 0))),
                credit=Decimal(str(line_data.get('credit', 0))),
                description=line_data.get('description', ''),
            )

        if auto_post:
            post_journal_entry(entry.id, user=user)

        return entry


def post_journal_entry(entry_id, user=None):
    """
    Post a journal entry — makes it official.
    Updates all affected account balances.

    Raises:
        ValidationError if entry is not balanced or already posted.
    """
    with transaction.atomic():
        entry = JournalEntry.objects.select_for_update().get(pk=entry_id)

        if entry.status == JournalEntry.EntryStatus.POSTED:
            raise ValidationError("Bu yozuv allaqachon tasdiqlangan.")
        if entry.status == JournalEntry.EntryStatus.VOID:
            raise ValidationError("Bekor qilingan yozuvni tasdiqlash mumkin emas.")

        if not entry.is_balanced:
            raise ValidationError(
                f"Yozuv balansi teng emas: "
                f"Debit={entry.total_debit}, Credit={entry.total_credit}"
            )

        # Check fiscal period
        if entry.fiscal_period and entry.fiscal_period.is_closed:
            raise ValidationError(
                f"Yopilgan davr: {entry.fiscal_period.name}. "
                "Yozuv kiritish mumkin emas."
            )

        entry.status = JournalEntry.EntryStatus.POSTED
        entry.posted_at = timezone.now()
        entry.save(update_fields=['status', 'posted_at', 'updated_at'])

        # Update account balances
        affected_accounts = set()
        for line in entry.lines.all():
            affected_accounts.add(line.account_id)

        for account_id in affected_accounts:
            account = Account.objects.get(pk=account_id)
            account.recalculate_balance()

        return entry


def void_journal_entry(entry_id, reason='', user=None):
    """
    Void a posted entry — creates a reverse entry.
    Original entry is marked as VOID but never deleted.
    """
    with transaction.atomic():
        entry = JournalEntry.objects.select_for_update().get(pk=entry_id)

        if entry.status != JournalEntry.EntryStatus.POSTED:
            raise ValidationError("Faqat tasdiqlangan yozuvlarni bekor qilish mumkin.")

        # Create reverse entry
        reverse_lines = []
        for line in entry.lines.all():
            reverse_lines.append({
                'account_id': line.account_id,
                'debit': line.credit,    # Swap
                'credit': line.debit,    # Swap
                'description': f"Teskari yozuv: {line.description}",
            })

        reverse_entry = create_journal_entry(
            description=f"BEKOR QILISH: {entry.entry_number} — {reason}",
            lines=reverse_lines,
            source_type=JournalEntry.SourceType.ADJUSTMENT,
            source_id=entry.id,
            source_description=f"Bekor qilish: {entry.entry_number}",
            user=user,
            auto_post=True,
        )

        # Mark original as void
        entry.status = JournalEntry.EntryStatus.VOID
        entry.voided_at = timezone.now()
        entry.voided_by = user
        entry.void_reason = reason
        entry.save(update_fields=[
            'status', 'voided_at', 'voided_by', 'void_reason', 'updated_at'
        ])

        return reverse_entry


# ═══════════════════════════════════════════════════
# 2. FINANCIAL REPORTS
# ═══════════════════════════════════════════════════

def get_trial_balance(start_date=None, end_date=None):
    """
    Trial Balance (Aylanma vedomost').
    Barcha hisoblar bo'yicha debit/credit yig'indilari.

    Returns:
        {
            'accounts': [
                {'code': '5010', 'name': 'Kassa', 'opening_debit': 0, 'opening_credit': 0,
                 'period_debit': 1000, 'period_credit': 500, 'closing_debit': 500, 'closing_credit': 0}
            ],
            'total_debit': ...,
            'total_credit': ...,
            'is_balanced': True
        }
    """
    if not end_date:
        end_date = timezone.now().date()
    if not start_date:
        start_date = end_date.replace(day=1)

    accounts = Account.objects.filter(is_active=True).order_by('code')
    result = []
    grand_debit = Decimal('0')
    grand_credit = Decimal('0')

    for account in accounts:
        posted_lines = JournalEntryLine.objects.filter(
            account=account,
            journal_entry__status='POSTED',
        )

        # Opening balance (before start_date)
        opening = posted_lines.filter(
            journal_entry__date__lt=start_date
        ).aggregate(
            debit=Sum('debit'),
            credit=Sum('credit')
        )
        opening_debit = opening['debit'] or Decimal('0')
        opening_credit = opening['credit'] or Decimal('0')

        # Period movements
        period = posted_lines.filter(
            journal_entry__date__gte=start_date,
            journal_entry__date__lte=end_date
        ).aggregate(
            debit=Sum('debit'),
            credit=Sum('credit')
        )
        period_debit = period['debit'] or Decimal('0')
        period_credit = period['credit'] or Decimal('0')

        # Closing balance
        closing_debit = opening_debit + period_debit
        closing_credit = opening_credit + period_credit

        # Skip empty accounts
        if period_debit == 0 and period_credit == 0 and opening_debit == 0 and opening_credit == 0:
            continue

        grand_debit += closing_debit
        grand_credit += closing_credit

        result.append({
            'code': account.code,
            'name': account.name,
            'account_type': account.account_type,
            'opening_debit': float(opening_debit),
            'opening_credit': float(opening_credit),
            'period_debit': float(period_debit),
            'period_credit': float(period_credit),
            'closing_debit': float(closing_debit),
            'closing_credit': float(closing_credit),
        })

    return {
        'start_date': str(start_date),
        'end_date': str(end_date),
        'accounts': result,
        'total_debit': float(grand_debit),
        'total_credit': float(grand_credit),
        'is_balanced': abs(grand_debit - grand_credit) < Decimal('0.01'),
    }


def get_balance_sheet(as_of_date=None):
    """
    Buxgalteriya balansi (Balans).
    Aktivlar = Passivlar (Majburiyatlar + Kapital)

    Returns:
        {
            'date': '2026-04-17',
            'assets': [...],
            'liabilities': [...],
            'equity': [...],
            'total_assets': 1000000,
            'total_liabilities': 600000,
            'total_equity': 400000,
            'is_balanced': True
        }
    """
    if not as_of_date:
        as_of_date = timezone.now().date()

    def _get_accounts_with_balance(account_type):
        accounts = Account.objects.filter(
            account_type=account_type,
            is_active=True
        ).order_by('code')

        items = []
        total = Decimal('0')

        for acc in accounts:
            lines = JournalEntryLine.objects.filter(
                account=acc,
                journal_entry__status='POSTED',
                journal_entry__date__lte=as_of_date
            ).aggregate(
                debit=Sum('debit'),
                credit=Sum('credit')
            )
            debit = lines['debit'] or Decimal('0')
            credit = lines['credit'] or Decimal('0')

            if account_type in [AccountType.ASSET, AccountType.EXPENSE]:
                balance = debit - credit
            else:
                balance = credit - debit

            if balance != 0:
                items.append({
                    'code': acc.code,
                    'name': acc.name,
                    'balance': float(balance),
                })
                total += balance

        return items, float(total)

    assets, total_assets = _get_accounts_with_balance(AccountType.ASSET)
    liabilities, total_liabilities = _get_accounts_with_balance(AccountType.LIABILITY)
    equity, total_equity = _get_accounts_with_balance(AccountType.EQUITY)

    # Net income adds to equity
    income_statement = get_income_statement(
        start_date=as_of_date.replace(month=1, day=1),
        end_date=as_of_date
    )
    net_income = income_statement.get('net_income', 0)
    total_equity += net_income

    return {
        'date': str(as_of_date),
        'assets': assets,
        'liabilities': liabilities,
        'equity': equity,
        'retained_earnings': net_income,
        'total_assets': total_assets,
        'total_liabilities': total_liabilities,
        'total_equity': total_equity,
        'total_liabilities_and_equity': total_liabilities + total_equity,
        'is_balanced': abs(total_assets - (total_liabilities + total_equity)) < 0.01,
    }


def get_income_statement(start_date=None, end_date=None):
    """
    Foyda va zarar hisoboti (P&L / Income Statement).

    Returns:
        {
            'revenues': [...],
            'expenses': [...],
            'total_revenue': 5000000,
            'total_expenses': 3000000,
            'net_income': 2000000
        }
    """
    if not end_date:
        end_date = timezone.now().date()
    if not start_date:
        start_date = end_date.replace(day=1)

    def _get_period_accounts(account_type):
        accounts = Account.objects.filter(
            account_type=account_type,
            is_active=True
        ).order_by('code')

        items = []
        total = Decimal('0')

        for acc in accounts:
            lines = JournalEntryLine.objects.filter(
                account=acc,
                journal_entry__status='POSTED',
                journal_entry__date__gte=start_date,
                journal_entry__date__lte=end_date,
            ).aggregate(
                debit=Sum('debit'),
                credit=Sum('credit')
            )
            debit = lines['debit'] or Decimal('0')
            credit = lines['credit'] or Decimal('0')

            if account_type == AccountType.REVENUE:
                balance = credit - debit
            else:
                balance = debit - credit

            if balance != 0:
                items.append({
                    'code': acc.code,
                    'name': acc.name,
                    'amount': float(balance),
                })
                total += balance

        return items, float(total)

    revenues, total_revenue = _get_period_accounts(AccountType.REVENUE)
    expenses, total_expenses = _get_period_accounts(AccountType.EXPENSE)

    return {
        'start_date': str(start_date),
        'end_date': str(end_date),
        'revenues': revenues,
        'expenses': expenses,
        'total_revenue': total_revenue,
        'total_expenses': total_expenses,
        'net_income': total_revenue - total_expenses,
        'profit_margin': round(
            ((total_revenue - total_expenses) / total_revenue * 100), 2
        ) if total_revenue > 0 else 0,
    }


def get_cash_flow(start_date=None, end_date=None):
    """
    Pul oqimlari hisoboti (Cash Flow Statement).
    Kassa va bank hisoblaridagi harakatlar.

    Returns:
        {
            'opening_cash': ...,
            'inflows': [...],
            'outflows': [...],
            'net_cash_flow': ...,
            'closing_cash': ...
        }
    """
    if not end_date:
        end_date = timezone.now().date()
    if not start_date:
        start_date = end_date.replace(day=1)

    # Cash accounts: 5000-5099 range (O'zbekiston BHM: pul mablag'lari)
    cash_accounts = Account.objects.filter(
        code__startswith='5',
        account_type=AccountType.ASSET,
        is_active=True
    ).order_by('code')

    cash_account_ids = list(cash_accounts.values_list('id', flat=True))

    # Opening balance (before start_date)
    opening = JournalEntryLine.objects.filter(
        account_id__in=cash_account_ids,
        journal_entry__status='POSTED',
        journal_entry__date__lt=start_date
    ).aggregate(
        debit=Sum('debit'),
        credit=Sum('credit')
    )
    opening_cash = float((opening['debit'] or 0) - (opening['credit'] or 0))

    # Period movements
    period_lines = JournalEntryLine.objects.filter(
        account_id__in=cash_account_ids,
        journal_entry__status='POSTED',
        journal_entry__date__gte=start_date,
        journal_entry__date__lte=end_date
    ).select_related('journal_entry')

    inflows = []
    outflows = []
    total_inflow = Decimal('0')
    total_outflow = Decimal('0')

    for line in period_lines:
        entry = line.journal_entry
        if line.debit > 0:
            inflows.append({
                'date': str(entry.date),
                'description': entry.description,
                'amount': float(line.debit),
                'source': entry.source_type,
                'entry_number': entry.entry_number,
            })
            total_inflow += line.debit
        elif line.credit > 0:
            outflows.append({
                'date': str(entry.date),
                'description': entry.description,
                'amount': float(line.credit),
                'source': entry.source_type,
                'entry_number': entry.entry_number,
            })
            total_outflow += line.credit

    net_cash_flow = float(total_inflow - total_outflow)

    return {
        'start_date': str(start_date),
        'end_date': str(end_date),
        'opening_cash': opening_cash,
        'total_inflow': float(total_inflow),
        'total_outflow': float(total_outflow),
        'net_cash_flow': net_cash_flow,
        'closing_cash': opening_cash + net_cash_flow,
        'inflows': sorted(inflows, key=lambda x: x['date'], reverse=True)[:50],
        'outflows': sorted(outflows, key=lambda x: x['date'], reverse=True)[:50],
    }


# ═══════════════════════════════════════════════════
# 3. TAX / QQS CALCULATIONS
# ═══════════════════════════════════════════════════

def calculate_vat(amount, tax_rate_id=None, tax_code='VAT_12'):
    """
    QQS hisoblash.

    Args:
        amount: Asosiy summa (bazaviy)
        tax_rate_id: TaxRate ID yoki
        tax_code: TaxRate code (masalan 'VAT_12')

    Returns:
        {'base_amount': 100000, 'tax_rate': 12.0, 'tax_amount': 12000, 'total': 112000}
    """
    if tax_rate_id:
        tax = TaxRate.objects.get(pk=tax_rate_id, is_active=True)
    else:
        try:
            tax = TaxRate.objects.get(code=tax_code, is_active=True)
        except TaxRate.DoesNotExist:
            return {
                'base_amount': float(amount),
                'tax_rate': 0,
                'tax_amount': 0,
                'total': float(amount),
            }

    base = Decimal(str(amount))
    tax_amount = base * tax.rate / 100

    return {
        'base_amount': float(base),
        'tax_rate': float(tax.rate),
        'tax_name': tax.name,
        'tax_amount': float(tax_amount.quantize(Decimal('0.01'))),
        'total': float((base + tax_amount).quantize(Decimal('0.01'))),
    }


# ═══════════════════════════════════════════════════
# 4. ACCOUNT BALANCE UTILITIES
# ═══════════════════════════════════════════════════

def get_account_balance(account_code, as_of_date=None):
    """Get balance for a single account."""
    if not as_of_date:
        as_of_date = timezone.now().date()

    try:
        account = Account.objects.get(code=account_code)
    except Account.DoesNotExist:
        return 0

    lines = JournalEntryLine.objects.filter(
        account=account,
        journal_entry__status='POSTED',
        journal_entry__date__lte=as_of_date
    ).aggregate(
        debit=Sum('debit'),
        credit=Sum('credit')
    )

    debit = lines['debit'] or Decimal('0')
    credit = lines['credit'] or Decimal('0')

    if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
        return float(debit - credit)
    return float(credit - debit)


def get_account_ledger(account_code, start_date=None, end_date=None):
    """Get detailed ledger for an account (all movements)."""
    if not end_date:
        end_date = timezone.now().date()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    try:
        account = Account.objects.get(code=account_code)
    except Account.DoesNotExist:
        return {'error': f'Hisob topilmadi: {account_code}'}

    lines = JournalEntryLine.objects.filter(
        account=account,
        journal_entry__status='POSTED',
        journal_entry__date__gte=start_date,
        journal_entry__date__lte=end_date
    ).select_related('journal_entry', 'journal_entry__created_by').order_by('journal_entry__date')

    running_balance = Decimal('0')
    # Get opening balance
    opening = JournalEntryLine.objects.filter(
        account=account,
        journal_entry__status='POSTED',
        journal_entry__date__lt=start_date
    ).aggregate(debit=Sum('debit'), credit=Sum('credit'))

    if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
        running_balance = (opening['debit'] or 0) - (opening['credit'] or 0)
    else:
        running_balance = (opening['credit'] or 0) - (opening['debit'] or 0)

    ledger = []
    for line in lines:
        if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]:
            running_balance += line.debit - line.credit
        else:
            running_balance += line.credit - line.debit

        ledger.append({
            'date': str(line.journal_entry.date),
            'entry_number': line.journal_entry.entry_number,
            'description': line.journal_entry.description,
            'debit': float(line.debit),
            'credit': float(line.credit),
            'balance': float(running_balance),
            'source_type': line.journal_entry.source_type,
            'created_by': line.journal_entry.created_by.full_name if line.journal_entry.created_by else None,
        })

    return {
        'account_code': account.code,
        'account_name': account.name,
        'start_date': str(start_date),
        'end_date': str(end_date),
        'opening_balance': float(running_balance - sum(
            l['debit'] - l['credit'] if account.account_type in [AccountType.ASSET, AccountType.EXPENSE]
            else l['credit'] - l['debit']
            for l in ledger
        )),
        'entries': ledger,
        'closing_balance': float(running_balance),
    }


# ═══════════════════════════════════════════════════
# 5. CHART OF ACCOUNTS SEEDER (O'zbekiston BHM)
# ═══════════════════════════════════════════════════

def seed_chart_of_accounts():
    """
    O'zbekiston BHM standarti bo'yicha standart hisoblar rejasini yaratish.
    Faqat yo'q bo'lgan hisoblarni yaratadi (idempotent).
    """
    # O'zbekiston Buxgalteriya hisobi standarti (21-son BHMS asosida)
    accounts_data = [
        # ═══ ASOSIY VOSITALAR VA BOSHQA UZOQ MUDDATLI AKTIVLAR (01-09) ═══
        ('0100', 'Asosiy vositalar', AccountType.ASSET, None, True),
        ('0200', 'Nomoddiy aktivlar', AccountType.ASSET, None, True),
        ('0400', 'Asosiy vositalarning eskirishi', AccountType.CONTRA, None, True),

        # ═══ ISHLAB CHIQARISH ZAHIRALARI (10-19) ═══
        ('1000', 'Materiallar', AccountType.ASSET, None, True),
        ('1010', 'Xom ashyo va materiallar', AccountType.ASSET, '1000', True),
        ('1020', 'Sotib olingan yarim tayyor buyumlar', AccountType.ASSET, '1000', True),
        ('1030', 'Yoqilg\'i', AccountType.ASSET, '1000', True),
        ('1040', 'Ehtiyot qismlar', AccountType.ASSET, '1000', True),
        ('1050', 'Qurilish materiallari', AccountType.ASSET, '1000', True),
        ('1060', 'Idish va idish materiallari', AccountType.ASSET, '1000', True),
        ('1080', 'Kam baholi va tez eskiruvchi buyumlar', AccountType.ASSET, '1000', True),

        # ═══ ASOSIY ISHLAB CHIQARISH XARAJATLARI (20-29) ═══
        ('2000', 'Asosiy ishlab chiqarish', AccountType.EXPENSE, None, True),
        ('2010', 'Asosiy ishlab chiqarish xarajatlari', AccountType.EXPENSE, '2000', True),
        ('2100', 'Yordamchi ishlab chiqarish', AccountType.EXPENSE, None, True),
        ('2300', 'Brak bo\'yicha yo\'qotishlar', AccountType.EXPENSE, None, True),
        ('2500', 'Umumishlab chiqarish xarajatlari', AccountType.EXPENSE, None, True),
        ('2600', 'Umumxo\'jalik xarajatlari', AccountType.EXPENSE, None, True),

        # ═══ TAYYOR MAHSULOT VA TOVARLAR (28-29) ═══
        ('2800', 'Tayyor mahsulot', AccountType.ASSET, None, True),
        ('2810', 'Tayyor penoplast mahsuloti', AccountType.ASSET, '2800', True),
        ('2820', 'Tayyor dekor mahsuloti', AccountType.ASSET, '2800', True),
        ('2900', 'Tovarlar', AccountType.ASSET, None, True),

        # ═══ PUL MABLAG\'LARI (50-59) ═══
        ('5000', 'Pul mablag\'lari', AccountType.ASSET, None, True),
        ('5010', 'Kassa', AccountType.ASSET, '5000', True),
        ('5020', 'Hisob-kitob schyoti', AccountType.ASSET, '5000', True),
        ('5030', 'Chet el valyutasidagi schyotlar', AccountType.ASSET, '5000', True),
        ('5040', 'Boshqa schyotlar va pul mablag\'lari', AccountType.ASSET, '5000', True),
        ('5050', 'O\'tkazmalardagi pul mablag\'lari', AccountType.ASSET, '5000', True),

        # ═══ HISOB-KITOBLAR (40-49, 60-69) ═══
        ('4000', 'Mol yetkazib beruvchilar bilan hisob-kitoblar', AccountType.LIABILITY, None, True),
        ('4010', 'Xom ashyo yetkazib beruvchilar', AccountType.LIABILITY, '4000', True),
        ('4020', 'Xizmat ko\'rsatuvchilar', AccountType.LIABILITY, '4000', True),

        ('4800', 'Xaridorlar va buyurtmachilar bilan hisob-kitoblar', AccountType.ASSET, None, True),
        ('4810', 'Ulgurji xaridorlar', AccountType.ASSET, '4800', True),
        ('4820', 'Chakana xaridorlar', AccountType.ASSET, '4800', True),

        ('6400', 'Budjetga to\'lovlar bo\'yicha hisob-kitoblar', AccountType.LIABILITY, None, True),
        ('6410', 'QQS (Qo\'shilgan qiymat solig\'i)', AccountType.LIABILITY, '6400', True),
        ('6420', 'Foyda solig\'i', AccountType.LIABILITY, '6400', True),
        ('6430', 'Boshqa soliqlar', AccountType.LIABILITY, '6400', True),

        ('6500', 'Mehnatga haq to\'lash bo\'yicha hisob-kitoblar', AccountType.LIABILITY, None, True),
        ('6510', 'Ish haqi', AccountType.LIABILITY, '6500', True),
        ('6520', 'Ijtimoiy sug\'urta ajratmalari', AccountType.LIABILITY, '6500', True),

        ('6700', 'Turli debitorlar va kreditorlar', AccountType.LIABILITY, None, True),

        # ═══ KAPITAL VA ZAXIRALAR (80-89) ═══
        ('8000', 'Kapital va zaxiralar', AccountType.EQUITY, None, True),
        ('8300', 'Ustav kapitali', AccountType.EQUITY, '8000', True),
        ('8400', 'Zaxira kapitali', AccountType.EQUITY, '8000', True),
        ('8500', 'Taqsimlanmagan foyda', AccountType.EQUITY, '8000', True),

        # ═══ DAROMADLAR (90-91) ═══
        ('9000', 'Daromadlar', AccountType.REVENUE, None, True),
        ('9010', 'Tayyor mahsulot sotishdan tushgan tushum', AccountType.REVENUE, '9000', True),
        ('9020', 'Xizmat ko\'rsatishdan daromad', AccountType.REVENUE, '9000', True),
        ('9030', 'Boshqa operatsion daromadlar', AccountType.REVENUE, '9000', True),

        # ═══ XARAJATLAR (90-94) ═══
        ('9100', 'Sotilgan mahsulot tannarxi', AccountType.EXPENSE, None, True),
        ('9200', 'Davr xarajatlari', AccountType.EXPENSE, None, True),
        ('9210', 'Sotish xarajatlari', AccountType.EXPENSE, '9200', True),
        ('9220', 'Ma\'muriy xarajatlar', AccountType.EXPENSE, '9200', True),
        ('9230', 'Boshqa operatsion xarajatlar', AccountType.EXPENSE, '9200', True),
        ('9310', 'Foizlarni to\'lash xarajatlari', AccountType.EXPENSE, None, True),
        ('9430', 'Foyda solig\'i bo\'yicha xarajatlar', AccountType.EXPENSE, None, True),

        # ═══ MOLIYAVIY NATIJALAR (95-99) ═══
        ('9900', 'Yakuniy moliyaviy natija', AccountType.EQUITY, None, True),
        ('9910', 'Hisobot davri foydasi (zarari)', AccountType.EQUITY, '9900', True),
    ]

    created_count = 0
    for code, name, acc_type, parent_code, is_system in accounts_data:
        parent = None
        if parent_code:
            parent = Account.objects.filter(code=parent_code).first()

        _, created = Account.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'account_type': acc_type,
                'parent': parent,
                'is_system': is_system,
                'description': '',
            }
        )
        if created:
            created_count += 1

    return created_count


def seed_default_tax_rates():
    """Standart soliq stavkalarini yaratish."""
    rates = [
        ('VAT_12', 'QQS 12%', Decimal('12.00'), "O'zbekiston standart QQS stavkasi"),
        ('VAT_0', 'QQS 0% (Imtiyozli)', Decimal('0.00'), "QQS imtiyozi"),
        ('EXEMPT', 'QQS dan ozod', Decimal('0.00'), "QQS dan ozod operatsiyalar"),
    ]

    created_count = 0
    for code, name, rate, desc in rates:
        _, created = TaxRate.objects.get_or_create(
            code=code,
            defaults={
                'name': name,
                'rate': rate,
                'description': desc,
            }
        )
        if created:
            created_count += 1

    return created_count
