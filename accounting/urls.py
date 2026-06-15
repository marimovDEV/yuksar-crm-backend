"""
Accounting URL Configuration.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AccountViewSet, JournalEntryViewSet,
    FiscalPeriodViewSet, TaxRateViewSet,
    TrialBalanceView, BalanceSheetView,
    IncomeStatementView, CashFlowView,
    VATCalculatorView, AccountingSummaryView,
)

router = DefaultRouter()
router.register(r'accounts', AccountViewSet, basename='account')
router.register(r'journal-entries', JournalEntryViewSet, basename='journal-entry')
router.register(r'fiscal-periods', FiscalPeriodViewSet, basename='fiscal-period')
router.register(r'tax-rates', TaxRateViewSet, basename='tax-rate')

urlpatterns = [
    path('', include(router.urls)),

    # Financial Reports
    path('trial-balance/', TrialBalanceView.as_view(), name='trial-balance'),
    path('balance-sheet/', BalanceSheetView.as_view(), name='balance-sheet'),
    path('income-statement/', IncomeStatementView.as_view(), name='income-statement'),
    path('cash-flow/', CashFlowView.as_view(), name='cash-flow'),

    # Utilities
    path('vat-calculator/', VATCalculatorView.as_view(), name='vat-calculator'),
    path('vat-calculate/', VATCalculatorView.as_view(), name='vat-calculate'),  # frontend alias
    path('summary/', AccountingSummaryView.as_view(), name='accounting-summary'),
]
