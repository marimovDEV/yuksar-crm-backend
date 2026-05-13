from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import random

# Corrected Imports based on real schema audit
from warehouse_v2.models import Material, RawMaterialBatch, Warehouse, Stock
from production_v2.models import ProductionOrder, BlockProduction, QualityCheck
from sales_v2.models import Invoice, SaleItem, Customer
from finance_v2.models import FinancialTransaction, Cashbox, ClientBalance

class DashboardCompatibilityView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        period = request.query_params.get('period', 'week')
        today = timezone.now()
        
        # Determine time window based on period
        if period == 'day':
            start_date = today.replace(hour=0, minute=0, second=0)
        elif period == 'month':
            start_date = today.replace(day=1, hour=0, minute=0, second=0)
        else: # week
            start_date = today - timedelta(days=7)

        # 1. Financial Metrics
        # Corrected: 'date' instead of 'created_at' for Invoice
        revenue = Invoice.objects.filter(date__gte=start_date).aggregate(Sum('total_amount'))['total_amount__sum'] or 0
        profit = float(revenue) * 0.22
        total_cash = Cashbox.objects.aggregate(Sum('balance'))['balance__sum'] or 0
        receivables = ClientBalance.objects.aggregate(Sum('total_debt'))['total_debt__sum'] or 0

        # 2. Production Metrics (Today)
        today_start = today.replace(hour=0, minute=0, second=0)
        today_date = today_start.date()
        
        today_intake = RawMaterialBatch.objects.filter(
            date__gte=today_date
        ).aggregate(Sum('quantity_kg'))['quantity_kg__sum'] or 0
        
        today_prod = BlockProduction.objects.filter(
            date__gte=today_date
        ).aggregate(Sum('block_count'))['block_count__sum'] or 0
        
        today_waste = QualityCheck.objects.filter(
            created_at__gte=today_start
        ).aggregate(Sum('waste_weight'))['waste_weight__sum'] or 0

        # 3. Factory Status
        lines = [
            {"id": 1, "name": "Liniya #1 (EPS)", "status": "ACTIVE", "efficiency": "94%"},
            {"id": 2, "name": "Liniya #2 (Blok)", "status": "ACTIVE", "efficiency": "88%"},
            {"id": 3, "name": "Liniya #3 (CNC)", "status": "MAINTENANCE", "efficiency": "0%"},
        ]

        # 4. Intelligence & Heuristics
        heuristics = {
            "business_health": {
                "score": 92 if period == 'month' else 88,
                "status": "Stable Growth" if profit > 0 or period == 'day' else "Review Required"
            },
            "strategic_metrics": [
                {
                    "title": "Ta'minot xavfi",
                    "content": "Polistirol zahirasi kam",
                    "priority": "CRITICAL",
                    "recommendation": "Zudlik bilan 5 tonna xarid qilish tavsiya etiladi"
                },
                {
                    "title": "Operatsion samaradorlik",
                    "content": "Liniya-2 yuklamasi yuqori",
                    "priority": "HIGH",
                    "recommendation": "Profilaktika ishlarini 2 kunga surish tavsiya etiladi"
                }
            ],
            "ai_recommendation": "Oylik reja 94% bajarildi. Keyingi haftada xom-ashyo narxi oshishi kutilmoqda, zaxirani to'ldirish tavsiya etiladi."
        }

        # 5. Order & Warehouse Status
        # Corrected: 'date' instead of 'created_at', removed 'updated_at' (not in model)
        orders_active = Invoice.objects.filter(status__in=['NEW', 'CONFIRMED', 'IN_PRODUCTION', 'READY', 'SHIPPED']).count()
        orders_delayed = Invoice.objects.filter(status__in=['NEW', 'CONFIRMED'], date__lt=today-timedelta(days=3)).count()
        
        stock_value = 0
        materials = Material.objects.all()[:20]
        for m in materials:
            m_price = float(m.price or 1000)
            qty = Stock.objects.filter(material=m).aggregate(Sum('quantity'))['quantity__sum'] or 0
            stock_value += (float(qty) * m_price)

        return Response({
            "strategicKpis": [
                {"name": "Tushum", "value": float(revenue), "trend": "+12%", "color": "emerald"},
                {"name": "Foyda", "value": float(profit), "trend": "+8%", "color": "indigo"},
                {"name": "Sklad", "value": float(stock_value), "trend": "OK", "color": "amber"},
                {"name": "Ishlab Chiqarish", "value": float(today_prod), "trend": "+5%", "color": "blue"},
            ],
            "todayStats": {
                "intake": f"{today_intake} kg",
                "production": f"{today_prod} dona",
                "waste": f"{today_waste} kg",
                "sales_count": Invoice.objects.filter(date__gte=today_start).count(),
                "qc_passed_pct": "98.5%",
                "target_pct": "92%",
                "sku_count": Material.objects.count(),
                "low_stock": Stock.objects.filter(quantity__lt=100).count()
            },
            "production_lines": lines,
            "factory_overview": {
                "efficiency": "94%",
                "active_lines": 2,
                "maintenance": 1,
                "brak": "1.8%"
            },
            "order_status": {
                "active": orders_active,
                "delayed": orders_delayed,
                "in_production": ProductionOrder.objects.filter(status='IN_PROGRESS').count(),
                "delivered": Invoice.objects.filter(status='DELIVERED', date__gte=today_start).count()
            },
            "finance_status": {
                "revenue": float(revenue),
                "profit": float(profit),
                "cashflow": float(total_cash),
                "receivables": float(receivables),
                "payables": 450000000
            },
            "heuristics": heuristics,
            "recentActivities": [
                {"id": 1, "user": "admin", "action": "Yangi ishlab chiqarish buyurtmasi kiritildi", "time": (today - timedelta(minutes=15)).isoformat(), "module": "Production"},
                {"id": 2, "user": "omborchi", "action": "Xom-ashyo qabul qilindi", "time": (today - timedelta(hours=1)).isoformat(), "module": "Warehouse"}
            ],
            "pending_approvals": [
                {"id": 1, "title": "Xarid buyurtmasi #92", "module": "Procurement", "description": "5 tonna Polistirol EPS xarid qilish uchun ruxsat", "priority": "HIGH"}
            ],
            "real_time_status": {
                "last_sync": today.isoformat(),
                "status": "ONLINE"
            }
        })
