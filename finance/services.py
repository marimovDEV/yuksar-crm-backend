from django.db import transaction, models
from decimal import Decimal
from .models import Account, Transaction, TransactionEntry

def record_double_entry(description, entries, reference=None, user=None):
    """
    Creates a double-entry transaction.
    entries: list of {'account_code': str, 'debit': Decimal, 'credit': Decimal}
    """
    with transaction.atomic():
        # 1. Verify Balance
        total_debit = sum(Decimal(str(e.get('debit', 0))) for e in entries)
        total_credit = sum(Decimal(str(e.get('credit', 0))) for e in entries)
        
        if total_debit != total_credit:
            raise ValueError(f"Transaction unbalanced: Debit ({total_debit}) != Credit ({total_credit})")
            
        # 2. Create Parent Transaction
        tx = Transaction.objects.create(
            description=description,
            reference_number=reference,
            created_by=user
        )
        
        # 3. Create Entries
        for entry_data in entries:
            code = entry_data['account_code']
            account, _ = Account.objects.get_or_create(
                code=code,
                defaults={
                    'name': f"Account {code}",
                    'type': 'ASSET' if (code.startswith('1') or code.startswith('2')) else 'EXPENSE'
                }
            )
            TransactionEntry.objects.create(
                transaction=tx,
                account=account,
                debit=entry_data.get('debit', 0),
                credit=entry_data.get('credit', 0)
            )
            
        return tx

def get_account_balance(account_code):
    """
    Calculates the current balance for an account.
    Balance = Sum(Debits) - Sum(Credits) for Assets/Expenses
    Balance = Sum(Credits) - Sum(Debits) for Liabilities/Equity/Income
    """
    account, _ = Account.objects.get_or_create(
        code=account_code,
        defaults={
            'name': f"Account {account_code}",
            'type': 'ASSET' if (account_code.startswith('1') or account_code.startswith('2')) else 'EXPENSE'
        }
    )
    entries = TransactionEntry.objects.filter(account=account)
    
    debit_sum = entries.aggregate(models.Sum('debit'))['debit__sum'] or Decimal(0)
    credit_sum = entries.aggregate(models.Sum('credit'))['credit__sum'] or Decimal(0)
    
    if account.type in ['ASSET', 'EXPENSE']:
        return debit_sum - credit_sum
    else:
        return credit_sum - debit_sum
