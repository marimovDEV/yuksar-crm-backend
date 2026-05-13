"""
Accounting Views — REST API endpoints for accounting module.
"""

from rest_framework import viewsets, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import action
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from .models import Account, JournalEntry, JournalEntryLine, FiscalPeriod, TaxRate
from .serializers import (
    AccountSerializer, AccountTreeSerializer,
    JournalEntrySerializer, JournalEntryCreateSerializer,
    FiscalPeriodSerializer, TaxRateSerializer,
)
from .services import (
    create_journal_entry, post_journal_entry, void_journal_entry,
    get_trial_balance, get_balance_sheet, get_income_statement,
    get_cash_flow, calculate_vat, get_account_ledger,
    seed_chart_of_accounts, seed_default_tax_rates,
)
from accounts.permissions import IsAdmin, IsSuperAdmin


class IsAccountant(permissions.BasePermission):
    """Buxgalter yoki Admin roli."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        role_name = ''
        if getattr(request.user, 'role_obj', None):
            role_name = request.user.role_obj.name or request.user.role or ''
        else:
            role_name = request.user.role or ''
        return role_name in [
            'Bosh Admin', 'Admin', 'Buxgalter', 'Moliya boshqaruvchi',
            'SUPERADMIN', 'ADMIN', 'ACCOUNTANT', 'FINANCE_MANAGER'
        ]


class AccountViewSet(viewsets.ModelViewSet):
    """
    Hisoblar rejasi (Chart of Accounts) CRUD.
    System hisoblarini o'chirish mumkin emas.
    """
    queryset = Account.objects.all().order_by('code')
    serializer_class = AccountSerializer
    permission_classes = [IsAccountant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['account_type', 'is_active', 'parent']
    search_fields = ['code', 'name', 'description']
    ordering_fields = ['code', 'name', 'balance']

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        if account.is_system:
            return Response(
                {'error': "System hisobini o'chirish mumkin emas."},
                status=status.HTTP_403_FORBIDDEN
            )
        if account.entry_lines.exists():
            return Response(
                {'error': "Bu hisobda provodkalar mavjud. O'chirish mumkin emas."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'])
    def tree(self, request):
        """Tree view — faqat root hisoblar (parent=null)."""
        root_accounts = Account.objects.filter(
            parent__isnull=True, is_active=True
        ).order_by('code')
        serializer = AccountTreeSerializer(root_accounts, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def ledger(self, request, pk=None):
        """Account ledger — barcha harakatlar."""
        account = self.get_object()
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        from datetime import date as date_cls
        s = None
        e = None
        if start_date:
            try:
                s = date_cls.fromisoformat(start_date)
            except ValueError:
                pass
        if end_date:
            try:
                e = date_cls.fromisoformat(end_date)
            except ValueError:
                pass

        ledger = get_account_ledger(account.code, start_date=s, end_date=e)
        return Response(ledger)

    @action(detail=False, methods=['post'], permission_classes=[IsSuperAdmin])
    def seed(self, request):
        """BHM standart hisoblar rejasini yaratish."""
        count = seed_chart_of_accounts()
        tax_count = seed_default_tax_rates()
        return Response({
            'message': f'{count} hisob va {tax_count} soliq stavkasi yaratildi.',
            'accounts_created': count,
            'tax_rates_created': tax_count,
        })

    @action(detail=False, methods=['get'])
    def ledger_by_code(self, request):
        """Account ledger by code lookup."""
        code = request.query_params.get('code')
        if not code:
            return Response({'error': 'Code required'}, status=400)
        
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')

        from datetime import date as date_cls
        s = None
        e = None
        if start_date:
            try: s = date_cls.fromisoformat(start_date)
            except ValueError: pass
        if end_date:
            try: e = date_cls.fromisoformat(end_date)
            except ValueError: pass

        ledger = get_account_ledger(code, start_date=s, end_date=e)
        return Response(ledger)



class JournalEntryViewSet(viewsets.ModelViewSet):
    """
    Buxgalteriya yozuvlari (provodkalar) CRUD.
    """
    queryset = JournalEntry.objects.all().prefetch_related('lines', 'lines__account')
    serializer_class = JournalEntrySerializer
    permission_classes = [IsAccountant]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'source_type', 'date']
    search_fields = ['entry_number', 'description', 'reference']
    ordering_fields = ['date', 'entry_number', 'total_amount', 'created_at']

    def get_serializer_class(self):
        if self.action == 'create':
            return JournalEntryCreateSerializer
        return JournalEntrySerializer

    def create(self, request, *args, **kwargs):
        """Create a journal entry with lines."""
        data = request.data.copy()
        if 'lines_json' in data:
            import json
            try:
                data['lines'] = json.loads(data['lines_json'])
            except json.JSONDecodeError:
                return Response({'error': 'Invalid lines_json format'}, status=400)

        serializer = JournalEntryCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        validated_data = serializer.validated_data

        try:
            entry = create_journal_entry(
                description=validated_data['description'],
                attachment=validated_data.get('attachment'),
                lines=[{
                    'account_code': l.get('account_code'),
                    'account_id': l.get('account_id'),
                    'debit': l.get('debit', 0),
                    'credit': l.get('credit', 0),
                    'description': l.get('description', ''),
                } for l in data['lines']],
                source_type=data.get('source_type', 'MANUAL'),
                source_id=data.get('source_id'),
                source_description=data.get('source_description', ''),
                reference=data.get('reference', ''),
                date_value=data.get('date'),
                user=request.user,
                auto_post=data.get('auto_post', False),
                tax_rate_id=data.get('tax_rate_id'),
            )
            return Response(
                JournalEntrySerializer(entry).data,
                status=status.HTTP_201_CREATED
            )
        except DjangoValidationError as e:
            return Response(
                {'error': str(e.message if hasattr(e, 'message') else e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    def destroy(self, request, *args, **kwargs):
        """Soft delete — actually void instead of delete."""
        entry = self.get_object()
        if entry.status == 'POSTED':
            return Response(
                {'error': "Tasdiqlangan yozuvni o'chirish mumkin emas. Bekor qiling."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if entry.status == 'VOID':
            return Response(
                {'error': "Bu yozuv allaqachon bekor qilingan."},
                status=status.HTTP_400_BAD_REQUEST
            )
        # Only drafts can be deleted
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def post_entry(self, request, pk=None):
        """Yozuvni tasdiqlash (post)."""
        try:
            entry = post_journal_entry(pk, user=request.user)
            return Response(JournalEntrySerializer(entry).data)
        except DjangoValidationError as e:
            return Response(
                {'error': str(e.message if hasattr(e, 'message') else e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def void_entry(self, request, pk=None):
        """Yozuvni bekor qilish (void)."""
        reason = request.data.get('reason', '')
        try:
            reverse_entry = void_journal_entry(pk, reason=reason, user=request.user)
            return Response({
                'message': 'Yozuv bekor qilindi.',
                'reverse_entry': JournalEntrySerializer(reverse_entry).data,
            })
        except DjangoValidationError as e:
            return Response(
                {'error': str(e.message if hasattr(e, 'message') else e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class FiscalPeriodViewSet(viewsets.ModelViewSet):
    """Hisobot davrlari CRUD."""
    queryset = FiscalPeriod.objects.all()
    serializer_class = FiscalPeriodSerializer
    permission_classes = [IsAccountant]

    def destroy(self, request, *args, **kwargs):
        period = self.get_object()
        if period.is_closed:
            return Response(
                {'error': "Yopilgan davrni o'chirish mumkin emas."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], permission_classes=[IsSuperAdmin])
    def close(self, request, pk=None):
        """Davrni yopish."""
        period = self.get_object()
        if period.is_closed:
            return Response(
                {'error': "Bu davr allaqachon yopilgan."},
                status=status.HTTP_400_BAD_REQUEST
            )
        period.close(request.user)
        return Response(FiscalPeriodSerializer(period).data)


class TaxRateViewSet(viewsets.ModelViewSet):
    """Soliq stavkalari CRUD — faqat SuperAdmin."""
    queryset = TaxRate.objects.all()
    serializer_class = TaxRateSerializer
    permission_classes = [IsSuperAdmin]


# ═══════════════════════════════════════════════════
# REPORT VIEWS
# ═══════════════════════════════════════════════════

class TrialBalanceView(APIView):
    """Aylanma vedomost' (Trial Balance)."""
    permission_classes = [IsAccountant]

    def get(self, request):
        from datetime import date as date_cls
        start = request.query_params.get('start_date')
        end = request.query_params.get('end_date')
        s = None
        e = None
        if start:
            try:
                s = date_cls.fromisoformat(start)
            except ValueError:
                pass
        if end:
            try:
                e = date_cls.fromisoformat(end)
            except ValueError:
                pass
        return Response(get_trial_balance(start_date=s, end_date=e))


class BalanceSheetView(APIView):
    """Buxgalteriya balansi (Balance Sheet)."""
    permission_classes = [IsAccountant]

    def get(self, request):
        from datetime import date as date_cls
        as_of = request.query_params.get('date')
        d = None
        if as_of:
            try:
                d = date_cls.fromisoformat(as_of)
            except ValueError:
                pass
        return Response(get_balance_sheet(as_of_date=d))


class IncomeStatementView(APIView):
    """Foyda va zarar hisoboti (P&L / Income Statement)."""
    permission_classes = [IsAccountant]

    def get(self, request):
        from datetime import date as date_cls
        start = request.query_params.get('start_date')
        end = request.query_params.get('end_date')
        s = None
        e = None
        if start:
            try:
                s = date_cls.fromisoformat(start)
            except ValueError:
                pass
        if end:
            try:
                e = date_cls.fromisoformat(end)
            except ValueError:
                pass
        return Response(get_income_statement(start_date=s, end_date=e))


class CashFlowView(APIView):
    """Pul oqimlari hisoboti (Cash Flow)."""
    permission_classes = [IsAccountant]

    def get(self, request):
        from datetime import date as date_cls
        start = request.query_params.get('start_date')
        end = request.query_params.get('end_date')
        s = None
        e = None
        if start:
            try:
                s = date_cls.fromisoformat(start)
            except ValueError:
                pass
        if end:
            try:
                e = date_cls.fromisoformat(end)
            except ValueError:
                pass
        return Response(get_cash_flow(start_date=s, end_date=e))


class VATCalculatorView(APIView):
    """QQS hisoblash kalkulyator."""
    permission_classes = [IsAccountant]

    def post(self, request):
        amount = request.data.get('amount')
        tax_rate_id = request.data.get('tax_rate_id')
        tax_code = request.data.get('tax_code', 'VAT_12')

        if not amount:
            return Response(
                {'error': 'Summa ko\'rsatilishi kerak.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            result = calculate_vat(amount, tax_rate_id=tax_rate_id, tax_code=tax_code)
            return Response(result)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AccountingSummaryView(APIView):
    """
    Buxgalter dashboard uchun umumiy ma'lumotlar.
    Kassa, debitorlik, kreditorlik, foyda — bir marta so'rov bilan.
    """
    permission_classes = [IsAccountant]

    def get(self, request):
        from .services import get_account_balance
        from django.utils import timezone
        from datetime import timedelta

        today = timezone.now().date()
        month_start = today.replace(day=1)

        # Key balances
        cash_balance = get_account_balance('5010', as_of_date=today)
        bank_balance = get_account_balance('5020', as_of_date=today)
        receivables = get_account_balance('4800', as_of_date=today)
        payables = get_account_balance('4000', as_of_date=today)
        raw_materials = get_account_balance('1000', as_of_date=today)
        finished_goods = get_account_balance('2800', as_of_date=today)

        # Monthly P&L
        pl = get_income_statement(start_date=month_start, end_date=today)

        # Recent entries
        recent_entries = JournalEntry.objects.filter(
            status='POSTED'
        ).order_by('-date', '-created_at')[:10]

        from .serializers import JournalEntrySerializer
        recent_data = JournalEntrySerializer(recent_entries, many=True).data

        # Monthly totals
        from django.db.models import Sum
        monthly_lines = JournalEntryLine.objects.filter(
            journal_entry__status='POSTED',
            journal_entry__date__gte=month_start,
            journal_entry__date__lte=today,
        ).aggregate(
            total_debit=Sum('debit'),
            total_credit=Sum('credit'),
        )

        return Response({
            'balances': {
                'cash': cash_balance,
                'bank': bank_balance,
                'total_cash': cash_balance + bank_balance,
                'receivables': receivables,
                'payables': abs(payables),
                'raw_materials': raw_materials,
                'finished_goods': finished_goods,
            },
            'monthly_pl': {
                'revenue': pl['total_revenue'],
                'expenses': pl['total_expenses'],
                'net_income': pl['net_income'],
                'profit_margin': pl['profit_margin'],
            },
            'monthly_totals': {
                'total_debit': float(monthly_lines['total_debit'] or 0),
                'total_credit': float(monthly_lines['total_credit'] or 0),
            },
            'recent_entries': recent_data,
            'entry_count': JournalEntry.objects.count(),
            'posted_count': JournalEntry.objects.filter(status='POSTED').count(),
            'draft_count': JournalEntry.objects.filter(status='DRAFT').count(),
        })
