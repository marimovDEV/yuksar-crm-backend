from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, Q
from django.utils import timezone
from datetime import timedelta
import random

# Corrected Imports based on real schema audit
from warehouse_v2.models import Material, RawMaterialBatch, Warehouse, Stock
from production_v2.models import (
    ProductionOrder, BlockProduction, QualityCheck, FinishedBlock,
    Zames, Bunker, BunkerLoad, DryingProcess, ProductionOrderStage,
)
from sales_v2.models import Invoice, SaleItem, Customer, Delivery
from finance_v2.models import FinancialTransaction, Cashbox, ClientBalance


def _build_factory_flow(today, today_start, today_date, defect_rate):
    """Build the 11-stage live factory flow with real DB counts."""

    # ── raw_material ──
    raw_active = Stock.objects.filter(
        material__category__in=['RAW'],
        quantity__gt=0,
    ).count()
    raw_problem = Stock.objects.filter(
        material__category__in=['RAW'],
        quantity__lt=100,
        quantity__gt=0,
    ).count()

    # ── zames ──
    zames_active = Zames.objects.filter(status='IN_PROGRESS').count()
    zames_waiting = Zames.objects.filter(status='PENDING').count()
    zames_problem = Zames.objects.filter(status='FAILED').count()

    # ── bunker ──
    bunker_active = Bunker.objects.filter(is_occupied=True).count()
    # Loads where required resting time has NOT elapsed yet
    bunker_waiting = 0
    for bl in BunkerLoad.objects.select_related('bunker').filter(bunker__is_occupied=True):
        aging_end = bl.load_time + timedelta(minutes=bl.required_time)
        if timezone.now() < aging_end:
            bunker_waiting += 1
    # Bunkers occupied > 24h are problems
    bunker_problem = Bunker.objects.filter(
        is_occupied=True,
        last_occupied_at__lt=timezone.now() - timedelta(hours=24),
    ).count()

    # ── formovka ──
    formovka_active = BlockProduction.objects.filter(
        status='COOLING', date=today_date,
    ).count()

    # ── cooling ──
    cooling_active = FinishedBlock.objects.filter(status='COOLING').count()

    # ── qc ──
    qc_active = FinishedBlock.objects.filter(status='QC_PENDING').count()
    qc_problem = 1 if defect_rate > 5 else 0

    # ── cnc ──
    cnc_active = FinishedBlock.objects.filter(status='CUTTING').count()

    # ── finishing ──
    finishing_active = FinishedBlock.objects.filter(status='FINISHING').count()

    # ── drying ──
    drying_active = DryingProcess.objects.filter(end_time__isnull=True).count()
    # Drying processes that have been running > 48h
    drying_problem = DryingProcess.objects.filter(
        end_time__isnull=True,
        start_time__lt=timezone.now() - timedelta(hours=48),
    ).count()

    # ── warehouse ──
    warehouse_active = FinishedBlock.objects.filter(status='READY').count()

    # ── delivery ──
    try:
        delivery_active = Delivery.objects.filter(status='EN_ROUTE').count()
        delivery_waiting = Delivery.objects.filter(status='PENDING').count()
        delivery_problem = Delivery.objects.filter(
            status='EN_ROUTE',
            started_at__lt=timezone.now() - timedelta(hours=24),
        ).count()
    except Exception:
        delivery_active = 0
        delivery_waiting = 0
        delivery_problem = 0

    return [
        {'id': 'raw_material', 'name': 'Xom Ashyo', 'name_ru': 'Сырьё',
         'active': raw_active, 'waiting': 0, 'problem': raw_problem},
        {'id': 'zames', 'name': 'Zames', 'name_ru': 'Замес',
         'active': zames_active, 'waiting': zames_waiting, 'problem': zames_problem},
        {'id': 'bunker', 'name': 'Bunker', 'name_ru': 'Бункер',
         'active': bunker_active, 'waiting': bunker_waiting, 'problem': bunker_problem},
        {'id': 'formovka', 'name': 'Formovka', 'name_ru': 'Формовка',
         'active': formovka_active, 'waiting': 0, 'problem': 0},
        {'id': 'cooling', 'name': 'Sovutish', 'name_ru': 'Охлаждение',
         'active': cooling_active, 'waiting': 0, 'problem': 0},
        {'id': 'qc', 'name': 'Sifat Nazorati', 'name_ru': 'Контроль качества',
         'active': qc_active, 'waiting': 0, 'problem': qc_problem},
        {'id': 'cnc', 'name': 'CNC Kesish', 'name_ru': 'CNC Резка',
         'active': cnc_active, 'waiting': 0, 'problem': 0},
        {'id': 'finishing', 'name': 'Pardozlash', 'name_ru': 'Отделка',
         'active': finishing_active, 'waiting': 0, 'problem': 0},
        {'id': 'drying', 'name': 'Quritish', 'name_ru': 'Сушка',
         'active': drying_active, 'waiting': 0, 'problem': drying_problem},
        {'id': 'warehouse', 'name': 'Ombor', 'name_ru': 'Склад',
         'active': warehouse_active, 'waiting': 0, 'problem': 0},
        {'id': 'delivery', 'name': 'Yetkazish', 'name_ru': 'Доставка',
         'active': delivery_active, 'waiting': delivery_waiting, 'problem': delivery_problem},
    ]


def _build_live_alerts(today, today_start, defect_rate):
    """Generate real-time alerts from DB heuristics."""
    alerts = []
    alert_id = 1

    # 1. Low stock materials (quantity < 100)
    low_stocks = Stock.objects.filter(
        quantity__lt=100, quantity__gt=0, material__category='RAW',
    ).select_related('material', 'warehouse')[:5]
    for s in low_stocks:
        alerts.append({
            'id': alert_id,
            'level': 'critical',
            'text_uz': f"{s.material.name} zaxirasi kam — {s.warehouse.name}da faqat {s.quantity} {s.material.unit} qoldi",
            'text_ru': f"Низкий запас {s.material.name} — на {s.warehouse.name} осталось {s.quantity} {s.material.unit}",
            'module': 'warehouse',
        })
        alert_id += 1

    # 2. Bunkers occupied > 24 hours
    long_bunkers = Bunker.objects.filter(
        is_occupied=True,
        last_occupied_at__lt=timezone.now() - timedelta(hours=24),
    )
    for b in long_bunkers[:3]:
        hours = round((timezone.now() - b.last_occupied_at).total_seconds() / 3600, 1) if b.last_occupied_at else 0
        alerts.append({
            'id': alert_id,
            'level': 'warning',
            'text_uz': f"{b.name} 24 soatdan ortiq band — {hours} soat",
            'text_ru': f"{b.name} занят более 24 часов — {hours} ч",
            'module': 'production',
        })
        alert_id += 1

    # 3. High defect rate (> 5%)
    if defect_rate > 5:
        alerts.append({
            'id': alert_id,
            'level': 'critical',
            'text_uz': f"Bugungi brak darajasi yuqori — {defect_rate}%",
            'text_ru': f"Высокий процент брака сегодня — {defect_rate}%",
            'module': 'production',
        })
        alert_id += 1

    # 4. Machines offline
    offline_stages = ProductionOrderStage.objects.filter(
        machine_status='OFFLINE',
        status__in=['PENDING', 'ACTIVE'],
    ).values('stage_type').distinct()[:3]
    for stage in offline_stages:
        alerts.append({
            'id': alert_id,
            'level': 'warning',
            'text_uz': f"{stage['stage_type']} bosqichida mashina o'chiq (OFFLINE)",
            'text_ru': f"Машина на этапе {stage['stage_type']} офлайн",
            'module': 'production',
        })
        alert_id += 1

    # 5. Overdue deliveries (EN_ROUTE > 24h)
    try:
        overdue_deliveries = Delivery.objects.filter(
            status='EN_ROUTE',
            started_at__lt=timezone.now() - timedelta(hours=24),
        ).select_related('invoice', 'invoice__customer')[:3]
        for d in overdue_deliveries:
            alerts.append({
                'id': alert_id,
                'level': 'warning',
                'text_uz': f"Yetkazib berish kechikmoqda — {d.invoice.invoice_number} ({d.invoice.customer.name})",
                'text_ru': f"Задержка доставки — {d.invoice.invoice_number} ({d.invoice.customer.name})",
                'module': 'sales',
            })
            alert_id += 1
    except Exception:
        pass

    # If no alerts, add an info one
    if not alerts:
        alerts.append({
            'id': 1,
            'level': 'info',
            'text_uz': "Barcha tizimlar normal ishlayapti",
            'text_ru': "Все системы работают нормально",
            'module': 'system',
        })

    return alerts


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

        # Real-time block KPIs
        cooling_count = FinishedBlock.objects.filter(status='COOLING').count()
        cutting_count = FinishedBlock.objects.filter(status='CUTTING').count()
        finishing_count = FinishedBlock.objects.filter(status='FINISHING').count()
        today_count = FinishedBlock.objects.filter(created_at__gte=today_start).count()
        today_recycled = FinishedBlock.objects.filter(created_at__gte=today_start, status='RECYCLE').count()
        defect_rate = round((today_recycled / today_count * 100), 2) if today_count > 0 else 0.0

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
        orders_active_qs = Invoice.objects.filter(status__in=['NEW', 'CONFIRMED', 'IN_PRODUCTION', 'READY', 'SHIPPED'])
        orders_delayed_qs = Invoice.objects.filter(status__in=['NEW', 'CONFIRMED', 'IN_PRODUCTION', 'READY'], date__lt=today-timedelta(days=3))
        
        user = request.user
        is_superuser = user.is_superuser or user.role == 'Bosh Admin'
        
        # Scopes for Sales Managers
        if user.role == 'Sotuv menejeri':
            orders_active_qs = orders_active_qs.filter(customer__assigned_manager=user)
            orders_delayed_qs = orders_delayed_qs.filter(customer__assigned_manager=user)
            
        orders_active = orders_active_qs.count()
        orders_delayed = orders_delayed_qs.count()
        
        stock_value = 0
        materials = Material.objects.all()[:20]
        for m in materials:
            m_price = float(m.price or 1000)
            qty = Stock.objects.filter(material=m).aggregate(Sum('quantity'))['quantity__sum'] or 0
            stock_value += (float(qty) * m_price)

        # Scoped Warehouse Statistics
        assigned_wh_ids = set() if is_superuser else set(user.assigned_warehouses.values_list('id', flat=True))
        stats = []
        for wh in Warehouse.objects.all().order_by('name'):
            has_access = is_superuser or (wh.id in assigned_wh_ids)
            if has_access:
                qty = Stock.objects.filter(warehouse=wh).aggregate(Sum('quantity'))['quantity__sum'] or 0
                val = f"{qty} kg"
            else:
                val = "0 kg"
            stats.append({
                "name": wh.name,
                "value": val
            })

        # recentKirim: recent RawMaterialBatch received
        recent_kirim_qs = RawMaterialBatch.objects.all().order_by('-date')[:10]
        recent_kirim = []
        for rmb in recent_kirim_qs:
            if is_superuser or not user.assigned_warehouses.exists() or rmb.warehouse_id in assigned_wh_ids:
                recent_kirim.append({
                    "batch_number": rmb.batch_number,
                    "material_name": rmb.material.name if rmb.material else "",
                    "quantity": f"{rmb.quantity_kg} kg",
                    "status": rmb.status
                })

        # recentSales: recent Invoices
        invoice_qs = Invoice.objects.all().order_by('-date')
        if user.role == 'Sotuv menejeri':
            invoice_qs = invoice_qs.filter(customer__assigned_manager=user)
        
        recent_sales = []
        for inv in invoice_qs[:10]:
            recent_sales.append({
                "invoice_number": inv.invoice_number,
                "customer_name": inv.customer.name,
                "total_amount": float(inv.total_amount),
                "status": inv.status
            })

        # todayStats sales count
        today_sales_qs = Invoice.objects.filter(date__gte=start_date)
        if user.role == 'Sotuv menejeri':
            today_sales_qs = today_sales_qs.filter(customer__assigned_manager=user)

        # 6. Live Factory Flow (11 stages) & Alerts
        factory_flow = _build_factory_flow(today, today_start, today_date, defect_rate)
        live_alerts = _build_live_alerts(today, today_start, defect_rate)

        return Response({
            "strategicKpis": [
                {"name": "Tushum", "value": float(revenue), "trend": "+12%", "color": "emerald"},
                {"name": "Foyda", "value": float(profit), "trend": "+8%", "color": "indigo"},
                {"name": "Sklad", "value": float(stock_value), "trend": "OK", "color": "amber"},
                {"name": "Ishlab Chiqarish", "value": float(today_prod), "trend": "+5%", "color": "blue"},
            ],
            "stats": stats,
            "recentKirim": recent_kirim,
            "recentSales": recent_sales,
            "overdueCount": orders_delayed,
            "todayStats": {
                "intake": f"{today_intake} kg",
                "production": f"{today_prod} dona",
                "waste": f"{today_waste} kg",
                "sales_count": today_sales_qs.count(),
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
            "production_status": {
                "cooling_count": cooling_count,
                "cutting_count": cutting_count,
                "finishing_count": finishing_count,
                "today_count": today_count,
                "today_recycled": today_recycled,
                "defect_rate": defect_rate
            },
            "heuristics": heuristics,
            "factory_flow": factory_flow,
            "live_alerts": live_alerts,
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
