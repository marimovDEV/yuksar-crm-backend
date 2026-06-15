from rest_framework import viewsets, permissions, views
from rest_framework.response import Response
from django.http import HttpResponse
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from .models import Cashbox, ExpenseCategory, FinancialTransaction, ClientBalance, InternalTransfer
from .serializers import (
    CashboxSerializer, ExpenseCategorySerializer, 
    FinancialTransactionSerializer, ClientBalanceSerializer,
    InternalTransferSerializer
)
from accounts.permissions import IsAdminOrSalesManager, IsAdmin, IsAccountant, IsAdminOrDirectorOrAccountant
from common_v2.mixins import NoDeleteMixin
from reports_v2.services import build_export_response_content

class CashboxViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    """Kassa — buxgalter to'liq boshqaradi, sotuv menejeri o'qiydi."""
    queryset = Cashbox.objects.all()
    serializer_class = CashboxSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSalesManager() | IsAccountant()]
        return [IsAdmin() | IsAccountant()]

class ExpenseCategoryViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    """Xarajat kategoriyalari — buxgalter boshqaradi."""
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSalesManager() | IsAccountant()]
        return [IsAdmin() | IsAccountant()]

class FinancialTransactionViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    """Moliyaviy tranzaksiyalar — buxgalter yaratadi/o'qiydi, sotuv menejeri o'qiydi."""
    queryset = FinancialTransaction.objects.all().order_by('-created_at')
    serializer_class = FinancialTransactionSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSalesManager() | IsAccountant()]
        if self.action == 'create':
            # Buxgalter va admin tranzaksiya yaratishi mumkin
            return [IsAdmin() | IsAccountant()]
        return [IsAdmin()]

    def perform_create(self, serializer):
        serializer.save(performed_by=self.request.user)

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.query_params.get('status')
        if status:
            qs = qs.filter(status=status)
        return qs

class InternalTransferViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    """Ichki o'tkazmalar — buxgalter boshqaradi."""
    queryset = InternalTransfer.objects.all().order_by('-created_at')
    serializer_class = InternalTransferSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSalesManager() | IsAccountant()]
        return [IsAdmin() | IsAccountant()]

    def perform_create(self, serializer):
        serializer.save(performed_by=self.request.user)

class ClientBalanceViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    """Mijoz balanslari — sotuv menejeri va buxgalter."""
    queryset = ClientBalance.objects.all()
    serializer_class = ClientBalanceSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSalesManager() | IsAccountant()]
        return [IsAdmin() | IsAccountant()]

class FinanceAnalyticsView(views.APIView):
    """Moliya analitikasi — buxgalter va direktor ko'radi."""
    permission_classes = [IsAdminOrDirectorOrAccountant]

    def get(self, request):
        today = timezone.now().date()
        start_date = today - timedelta(days=30)
        
        # Cashflow Chart Data (Actual vs Forecast)
        chart_data = []
        for i in range(30, -5, -1): # Include 5 days forecast
            date = today - timedelta(days=i)
            income = FinancialTransaction.objects.filter(type='INCOME', status='APPROVED', created_at__date=date).aggregate(Sum('amount'))['amount__sum'] or 0
            expense = FinancialTransaction.objects.filter(type='EXPENSE', status='APPROVED', created_at__date=date).aggregate(Sum('amount'))['amount__sum'] or 0
            
            # Forecasted amounts based on due_date
            forecast_income = FinancialTransaction.objects.filter(type='INCOME', status='PENDING', due_date__date=date).aggregate(Sum('amount'))['amount__sum'] or 0
            forecast_expense = FinancialTransaction.objects.filter(type='EXPENSE', status='PENDING', due_date__date=date).aggregate(Sum('amount'))['amount__sum'] or 0
            
            chart_data.append({
                'date': date.strftime('%d.%m'),
                'income': float(income),
                'expense': float(expense),
                'forecast_income': float(forecast_income),
                'forecast_expense': float(forecast_expense),
                'is_forecast': date > today
            })
            
        # Category Breakdown (Hierarchical level 1)
        categories = FinancialTransaction.objects.filter(
            type='EXPENSE', 
            status='APPROVED',
            created_at__date__gte=start_date
        ).values('category__name').annotate(total=Sum('amount'))
        
        category_data = [
            {'name': c['category__name'] or 'Boshqa', 'value': float(c['total'])} 
            for c in categories
        ]
        
        # Debt Summary
        customer_debt = ClientBalance.objects.filter(total_debt__gt=0).aggregate(Sum('total_debt'))['total_debt__sum'] or 0
        supplier_debt = ClientBalance.objects.filter(total_debt__lt=0).aggregate(Sum('total_debt'))['total_debt__sum'] or 0
        
        # Pending Approvals
        pending_count = FinancialTransaction.objects.filter(status='PENDING').count()
        
        return Response({
            'cashflow': chart_data,
            'categories': category_data,
            'summary': {
                'customer_debt': float(customer_debt),
                'supplier_debt': abs(float(supplier_debt)),
                'total_balance': float(Cashbox.objects.aggregate(Sum('balance'))['balance__sum'] or 0),
                'pending_approvals': pending_count,
                'overdue_count': ClientBalance.objects.filter(due_date__lt=today, total_debt__gt=0).count()
            }
        })


class FinanceExportView(views.APIView):
    """Moliya eksporti — faqat buxgalter va admin."""
    permission_classes = [IsAdminOrDirectorOrAccountant]

    def get(self, request):
        file_format = request.query_params.get('file_format') or request.query_params.get('export_format', 'PDF')
        file_format = file_format.upper()
        period = request.query_params.get('period', 'This Month')
        today = timezone.now().date()
        if period == 'Today':
            start_date = today
        elif period == 'Last 7 Days':
            start_date = today - timedelta(days=6)
        else:
            start_date = today.replace(day=1)

        transactions = FinancialTransaction.objects.filter(created_at__date__gte=start_date).select_related('cashbox', 'category', 'customer').order_by('-created_at')
        rows = [['Sana', 'Turi', 'Kassa', 'Bolim', 'Kategoriya', 'Mijoz', 'Summa', 'Izoh']]
        for tr in transactions:
            rows.append([
                tr.created_at.strftime('%Y-%m-%d %H:%M'),
                tr.type,
                tr.cashbox.name,
                tr.department,
                tr.category.name if tr.category else '',
                tr.customer.name if tr.customer else '',
                float(tr.amount),
                tr.description or '',
            ])
        rows.append([])
        rows.append(['Jami kirim', '', '', '', '', '', float(transactions.filter(type='INCOME').aggregate(s=Sum('amount'))['s'] or 0), ''])
        rows.append(['Jami chiqim', '', '', '', '', '', float(transactions.filter(type='EXPENSE').aggregate(s=Sum('amount'))['s'] or 0), ''])

        title = f'Finance export - {period}'
        content, extension, content_type = build_export_response_content(title, rows, file_format)
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="finance-export.{extension}"'
        return response
