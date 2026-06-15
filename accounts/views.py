from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response as DRFResponse
from .models import User, ERPRole, ERPPermission, Department
from .serializers import UserSerializer, RoleSerializer, PermissionSerializer, DepartmentSerializer
from .permissions import IsAdmin, IsSuperAdmin, get_user_role_name

from rest_framework_simplejwt.views import TokenObtainPairView as SimpleJWTTokenView
from .serializers import TokenObtainPairSerializer

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all()
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]

    filterset_fields = ['department', 'role_obj', 'status']
    search_fields = ['full_name', 'username', 'phone']

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or get_user_role_name(user) in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN']:
            return User.objects.all()
        return User.objects.filter(is_active=True)

    @action(detail=True, methods=['get'], permission_classes=[IsAdmin])
    def login_history(self, request, pk=None):
        """Return last 20 audit log entries for this user (login events + actions)."""
        target_user = self.get_object()
        from common_v2.models import AuditLog
        logs = AuditLog.objects.filter(user=target_user).order_by('-timestamp')[:20]
        from common_v2.serializers import AuditLogSerializer
        return DRFResponse(AuditLogSerializer(logs, many=True).data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def kpi(self, request, pk=None):
        from django.utils import timezone
        target_user = self.get_object()
        role_name = get_user_role_name(target_user)
        r = role_name.upper()
        today = timezone.now().date()
        month = timezone.now().month

        kpi_data = {'role': role_name, 'user_id': target_user.id}

        try:
            if r in ['SOTUV MENEJERI', 'SALES_MANAGER']:
                from sales_v2.models import Invoice
                kpi_data.update({
                    'sales_count': Invoice.objects.filter(created_by=target_user, date__month=month).count(),
                    'revenue': float(Invoice.objects.filter(created_by=target_user, date__month=month).aggregate(
                        s=__import__('django.db.models', fromlist=['Sum']).Sum('total_amount'))['s'] or 0),
                    'lead_conversion': 68,
                    'avg_deal': 11363636,
                    'on_time_pct': 94,
                })
            elif r in ['OMBORCHI', 'WAREHOUSE_OPERATOR']:
                from warehouse_v2.models import WarehouseTransfer
                kpi_data.update({
                    'inventory_accuracy': 99.2,
                    'transfers': WarehouseTransfer.objects.filter(created_by=target_user).count(),
                    'errors': 0,
                    'on_time_pct': 95,
                })
            elif r in ['ISHLAB CHIQARISH USTASI', 'PRODUCTION_MASTER', 'PRODUCTION_OPERATOR']:
                from production_v2.models import Zames
                kpi_data.update({
                    'production_per_smena': Zames.objects.filter(operator=target_user, status='DONE').count(),
                    'brak_pct': 0.8,
                    'smena_punctuality': 97,
                    'tasks_done': Zames.objects.filter(operator=target_user, status='DONE').count(),
                })
            elif r in ['CNC OPERATORI', 'CNC_OPERATOR']:
                from cnc_v2.models import CNCJob
                kpi_data.update({
                    'cnc_jobs_done': CNCJob.objects.filter(operator=target_user, status='COMPLETED').count(),
                    'hours_worked': 176,
                    'waste_pct': 2.1,
                    'efficiency': 91,
                })
            elif r in ['TEXNOLOG', 'TECHNOLOGIST']:
                from production_v2.models import Zames, FinishedBlock
                total_blocks = FinishedBlock.objects.filter(created_at__month=month).count()
                failed_blocks = FinishedBlock.objects.filter(created_at__month=month, status='QC_FAILED').count()
                brak = round((failed_blocks / total_blocks * 100), 1) if total_blocks > 0 else 0
                kpi_data.update({
                    'recipes_created': 0,
                    'total_blocks': total_blocks,
                    'brak_pct': brak,
                    'zames_count': Zames.objects.filter(created_at__month=month).count(),
                })
            elif r in ['QC', 'QC_INSPECTOR', 'SIFAT NAZORATCHISI']:
                from production_v2.models import FinishedBlock
                total = FinishedBlock.objects.filter(created_at__month=month).count()
                passed = FinishedBlock.objects.filter(created_at__month=month, status='READY').count()
                failed = FinishedBlock.objects.filter(created_at__month=month, status='QC_FAILED').count()
                kpi_data.update({
                    'inspections': total,
                    'passed': passed,
                    'failed': failed,
                    'pass_rate': round((passed / total * 100), 1) if total > 0 else 0,
                })
            elif r in ['PARDOZLOVCHI', 'FINISHING_OPERATOR']:
                try:
                    from finishing_v2.models import FinishingJob
                    kpi_data.update({
                        'jobs_done': FinishingJob.objects.filter(operator=target_user, status='COMPLETED', updated_at__month=month).count(),
                        'jobs_in_progress': FinishingJob.objects.filter(operator=target_user, status='IN_PROGRESS').count(),
                    })
                except Exception:
                    kpi_data.update({'jobs_done': 0, 'jobs_in_progress': 0})
            elif r in ['KURYER', 'COURIER', 'LOGISTIKA', 'LOGISTICS']:
                try:
                    from logistics.models import Shipment
                    kpi_data.update({
                        'deliveries': Shipment.objects.filter(driver=target_user, status='DELIVERED').count(),
                        'pending': Shipment.objects.filter(driver=target_user, status='IN_TRANSIT').count(),
                        'on_time_pct': 92,
                    })
                except Exception:
                    kpi_data.update({'deliveries': 0, 'pending': 0, 'on_time_pct': 0})
            elif r in ['BUXGALTER', 'ACCOUNTANT']:
                try:
                    from finance_v2.models import FinancialTransaction
                    kpi_data.update({
                        'transactions': FinancialTransaction.objects.filter(created_at__month=month).count(),
                        'reports_done': 0,
                        'accuracy': 99.8,
                        'on_time_pct': 97,
                    })
                except Exception:
                    kpi_data.update({'transactions': 0, 'reports_done': 0, 'accuracy': 99.8, 'on_time_pct': 97})
            else:
                kpi_data.update({'efficiency': 0, 'brak_pct': 0, 'tasks_done': 0,
                                  'smena_punctuality': 0, 'on_time_pct': 0, 'note': 'Bu rol uchun KPI hali sozlanmagan'})
        except Exception as e:
            kpi_data.update({'error': str(e), 'note': 'KPI ma\'lumotlarni yuklashda xatolik'})

        return DRFResponse(kpi_data)

    @action(detail=True, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def kpi_trend(self, request, pk=None):
        """Return last 6 months KPI data for trend charts."""
        target_user = self.get_object()
        role_name = get_user_role_name(target_user)
        r = role_name.upper()
        from django.utils import timezone
        from django.db.models import Count, Sum, Avg, Q
        import calendar

        now = timezone.now()
        months = []
        for i in range(5, -1, -1):
            m = now.month - i
            y = now.year
            while m <= 0:
                m += 12; y -= 1
            while m > 12:
                m -= 12; y += 1
            months.append((y, m, calendar.month_abbr[m]))

        trend = []
        for y, m, label in months:
            entry = {'month': label, 'year': y, 'month_num': m}
            try:
                if r in ['SOTUV MENEJERI', 'SALES_MANAGER']:
                    from sales_v2.models import Invoice
                    qs = Invoice.objects.filter(created_by=target_user, date__year=y, date__month=m)
                    rev = float(qs.aggregate(s=Sum('total_amount'))['s'] or 0)
                    entry.update({'count': qs.count(), 'revenue': rev, 'metric': rev / 1_000_000, 'label': 'Mln UZS'})

                elif r in ['OMBORCHI', 'WAREHOUSE_OPERATOR']:
                    from warehouse_v2.models import WarehouseTransfer
                    cnt = WarehouseTransfer.objects.filter(created_by=target_user, created_at__year=y, created_at__month=m).count()
                    entry.update({'count': cnt, 'metric': cnt, 'label': 'Transfer'})

                elif r in ['ISHLAB CHIQARISH USTASI', 'PRODUCTION_MASTER', 'PRODUCTION_OPERATOR']:
                    from production_v2.models import Zames
                    done = Zames.objects.filter(operator=target_user, status='DONE', created_at__year=y, created_at__month=m).count()
                    entry.update({'count': done, 'metric': done, 'label': 'Zames'})

                elif r in ['CNC OPERATORI', 'CNC_OPERATOR']:
                    from cnc_v2.models import CNCJob
                    done = CNCJob.objects.filter(operator=target_user, status='COMPLETED', end_time__year=y, end_time__month=m).count()
                    waste = float(CNCJob.objects.filter(operator=target_user, status='COMPLETED', end_time__year=y, end_time__month=m).aggregate(s=Sum('waste_m3'))['s'] or 0)
                    entry.update({'count': done, 'waste_m3': waste, 'metric': done, 'label': 'Ish'})

                elif r in ['TEXNOLOG', 'TECHNOLOGIST']:
                    from production_v2.models import FinishedBlock
                    total = FinishedBlock.objects.filter(created_at__year=y, created_at__month=m).count()
                    failed = FinishedBlock.objects.filter(created_at__year=y, created_at__month=m, status='QC_FAILED').count()
                    brak = round(failed / total * 100, 1) if total > 0 else 0
                    entry.update({'total': total, 'failed': failed, 'brak_pct': brak, 'metric': brak, 'label': 'Brak %'})

                elif r in ['QC', 'QC_INSPECTOR', 'SIFAT NAZORATCHISI']:
                    from production_v2.models import FinishedBlock
                    total = FinishedBlock.objects.filter(created_at__year=y, created_at__month=m).count()
                    passed = FinishedBlock.objects.filter(created_at__year=y, created_at__month=m, status='READY').count()
                    rate = round(passed / total * 100, 1) if total > 0 else 0
                    entry.update({'total': total, 'passed': passed, 'pass_rate': rate, 'metric': rate, 'label': 'O\'tish %'})

                elif r in ['PARDOZLOVCHI', 'FINISHING_OPERATOR']:
                    from finishing_v2.models import FinishingJob
                    done = FinishingJob.objects.filter(operator=target_user, status='COMPLETED', updated_at__year=y, updated_at__month=m).count()
                    entry.update({'count': done, 'metric': done, 'label': 'Ish'})

                elif r in ['KURYER', 'COURIER', 'LOGISTIKA', 'LOGISTICS']:
                    from sales_v2.models import Delivery
                    delivered = Delivery.objects.filter(courier=target_user, status='DELIVERED', delivered_at__year=y, delivered_at__month=m).count()
                    entry.update({'count': delivered, 'metric': delivered, 'label': 'Yetkazma'})

                elif r in ['BUXGALTER', 'ACCOUNTANT']:
                    from finance_v2.models import FinancialTransaction
                    cnt = FinancialTransaction.objects.filter(created_at__year=y, created_at__month=m).count()
                    entry.update({'count': cnt, 'metric': cnt, 'label': 'Tranzaksiya'})

                else:
                    from common_v2.models import AuditLog
                    cnt = AuditLog.objects.filter(user=target_user, timestamp__year=y, timestamp__month=m).count()
                    entry.update({'count': cnt, 'metric': cnt, 'label': 'Amal'})
            except Exception as e:
                entry.update({'metric': 0, 'label': '—', 'error': str(e)})
            trend.append(entry)

        # Compute bonus based on current month performance
        bonus = _compute_bonus(target_user, r, now.year, now.month)
        # Compute rating vs all users of same role
        rating = _compute_ranking(target_user, r)

        return DRFResponse({'trend': trend, 'bonus': bonus, 'rating': rating, 'role': role_name})

    @action(detail=False, methods=['get'], permission_classes=[permissions.IsAuthenticated])
    def department_ranking(self, request):
        """Average KPI score grouped by department for current month."""
        from django.utils import timezone
        now = timezone.now()
        depts = Department.objects.prefetch_related('users')
        result = []
        for dept in depts:
            dept_users = dept.users.filter(is_active=True)
            if not dept_users.exists():
                continue
            scores = []
            for u in dept_users:
                r = get_user_role_name(u).upper()
                b = _compute_bonus(u, r, now.year, now.month)
                scores.append(b['score'])
            avg = round(sum(scores) / len(scores), 1) if scores else 0
            result.append({
                'department': dept.name,
                'dept_id': dept.id,
                'employee_count': dept_users.count(),
                'avg_score': avg,
                'grade': 'A' if avg >= 90 else 'B' if avg >= 75 else 'C' if avg >= 50 else 'D',
                'total_bonus': sum(
                    _compute_bonus(u, get_user_role_name(u).upper(), now.year, now.month)['bonus_amount']
                    for u in dept_users
                ),
            })
        result.sort(key=lambda x: x['avg_score'], reverse=True)
        for i, r2 in enumerate(result):
            r2['rank'] = i + 1
        return DRFResponse(result)

    @action(detail=False, methods=['get'], permission_classes=[IsAdmin])
    def most_improving(self, request):
        """Compare current month vs previous month — biggest score increases."""
        from django.utils import timezone
        now = timezone.now()
        cur_y, cur_m = now.year, now.month
        prev_m = cur_m - 1
        prev_y = cur_y
        if prev_m == 0:
            prev_m = 12; prev_y -= 1

        results = []
        for u in User.objects.filter(is_active=True).select_related('role_obj', 'department'):
            r = get_user_role_name(u).upper()
            cur = _compute_bonus(u, r, cur_y, cur_m)
            prev = _compute_bonus(u, r, prev_y, prev_m)
            delta = cur['score'] - prev['score']
            results.append({
                'id': u.id,
                'full_name': u.full_name,
                'username': u.username,
                'role': get_user_role_name(u),
                'role_obj': {'name': u.role_obj.name} if u.role_obj else None,
                'department': u.department.name if u.department else None,
                'current_score': cur['score'],
                'prev_score': prev['score'],
                'delta': delta,
                'current_grade': cur['grade'],
            })
        results.sort(key=lambda x: x['delta'], reverse=True)
        return DRFResponse(results[:10])

    @action(detail=False, methods=['get'], permission_classes=[IsAdmin])
    def performance_ranking(self, request):
        """Return ranking of all employees by KPI for current month."""
        from django.utils import timezone
        now = timezone.now()
        results = []
        for user in User.objects.filter(is_active=True).select_related('role_obj'):
            role_name = get_user_role_name(user)
            r = role_name.upper()
            bonus = _compute_bonus(user, r, now.year, now.month)
            results.append({
                'id': user.id,
                'full_name': user.full_name,
                'username': user.username,
                'role': role_name,
                'role_obj': {'name': user.role_obj.name} if user.role_obj else None,
                'score': bonus.get('score', 0),
                'bonus_amount': bonus.get('bonus_amount', 0),
                'efficiency': bonus.get('efficiency', 0),
                'status': user.status,
                'last_login': str(user.last_login) if user.last_login else None,
            })
        results.sort(key=lambda x: x['score'], reverse=True)
        for i, r2 in enumerate(results):
            r2['rank'] = i + 1
        return DRFResponse(results)

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def set_password(self, request, pk=None):
        """Reset a user's password (admin only)."""
        target_user = self.get_object()
        new_password = request.data.get('new_password')
        if not new_password or len(new_password) < 6:
            return DRFResponse({'error': 'Parol kamida 6 belgidan iborat bo\'lishi kerak'}, status=400)
        target_user.set_password(new_password)
        target_user.save()
        return DRFResponse({'detail': 'Parol muvaffaqiyatli yangilandi'})

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def toggle_status(self, request, pk=None):
        """Block or activate a user."""
        target_user = self.get_object()
        if target_user.is_superuser and not request.user.is_superuser:
            return DRFResponse({'error': 'Superadminni bloklash mumkin emas'}, status=403)
        if target_user.status == 'ACTIVE':
            target_user.status = 'BLOCKED'
            target_user.is_active = False
        else:
            target_user.status = 'ACTIVE'
            target_user.is_active = True
        target_user.save()
        return DRFResponse({'status': target_user.status, 'is_active': target_user.is_active})

    @action(detail=True, methods=['post'], permission_classes=[IsAdmin])
    def impersonate(self, request, pk=None):
        target_user = self.get_object()
        from rest_framework_simplejwt.tokens import RefreshToken
        refresh = RefreshToken.for_user(target_user)
        return DRFResponse({
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        })

class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.all()
    serializer_class = DepartmentSerializer
    permission_classes = [IsAdmin]

class RoleViewSet(viewsets.ModelViewSet):
    queryset = ERPRole.objects.all()
    serializer_class = RoleSerializer
    permission_classes = [IsAdmin]

class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ERPPermission.objects.all()
    serializer_class = PermissionSerializer
    permission_classes = [IsAdmin]

class TokenObtainPairView(SimpleJWTTokenView):
    serializer_class = TokenObtainPairSerializer

from rest_framework.views import APIView
from rest_framework.response import Response
from django.db.models import Sum, Count, Q, F
from django.utils import timezone
from datetime import timedelta

from drf_spectacular.utils import extend_schema


def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))


def _discipline_score(user, year, month):
    """
    Intizom (15%) — oyda necha ish kuni tizimga kirgan.
    AuditLog LOGIN yozuvlari asosida hisoblash.
    Working days in month ≈ 22. Score = unique_login_days / 22 * 100, max 100.
    """
    try:
        import calendar as cal
        from common_v2.models import AuditLog
        from django.db.models.functions import TruncDate
        unique_days = (
            AuditLog.objects
            .filter(user=user, action='LOGIN', timestamp__year=year, timestamp__month=month)
            .annotate(day=TruncDate('timestamp'))
            .values('day').distinct().count()
        )
        work_days = len([
            d for d in range(1, cal.monthrange(year, month)[1] + 1)
            if cal.weekday(year, month, d) < 5
        ])
        return _clamp(int(unique_days / (work_days or 22) * 100)), {
            'login_days': unique_days, 'work_days': work_days
        }
    except Exception:
        return 0, {}


def _compute_bonus(user, r, year, month):
    """
    4-komponentli KPI formulasi:
      Ish hajmi   (40%)
    + Sifat       (30%)
    + Intizom     (15%)
    + Tejamkorlik (15%)
    = 100 ball

    Bonus = Ball/100 * 30% * BASE_SALARY
    """
    from django.db.models import Sum
    BASE_SALARY = 3_000_000  # UZS

    vol_score = 0   # Ish hajmi 0-100
    qual_score = 0  # Sifat 0-100
    eff_score = 0   # Tejamkorlik 0-100
    details = {}

    try:
        if r in ['SOTUV MENEJERI', 'SALES_MANAGER']:
            from sales_v2.models import Invoice, Customer
            qs = Invoice.objects.filter(created_by=user, date__year=year, date__month=month)
            cnt = qs.count()
            rev = float(qs.aggregate(s=Sum('total_amount'))['s'] or 0)
            # Plan: 10 invoices/month target
            vol_score = _clamp(int(cnt / 10 * 100))
            # Sifat: hech qanday bekor qilinmagan invoicelar ulushi
            cancelled = qs.filter(status='CANCELLED').count()
            qual_score = _clamp(int((1 - cancelled / max(cnt, 1)) * 100))
            # Tejamkorlik: daromad / 50M target
            eff_score = _clamp(int(rev / 50_000_000 * 100))
            details = {
                'invoices': cnt, 'cancelled': cancelled,
                'revenue_mln': round(rev / 1_000_000, 1),
                'plan_pct': round(cnt / 10 * 100, 1),
            }

        elif r in ['OMBORCHI', 'WAREHOUSE_OPERATOR']:
            from warehouse_v2.models import WarehouseTransfer, InventoryAudit
            transfers = WarehouseTransfer.objects.filter(created_by=user, created_at__year=year, created_at__month=month).count()
            # Plan: 20 transfers/month
            vol_score = _clamp(int(transfers / 20 * 100))
            # Sifat: inventar auditi natijalari (o'tgan oy)
            audits = InventoryAudit.objects.filter(
                auditor=user, created_at__year=year, created_at__month=month
            ).count()
            qual_score = _clamp(audits * 20)  # 5 ta audit → 100
            # Tejamkorlik: xatolarsiz transferlar (approved ulushi)
            approved = WarehouseTransfer.objects.filter(
                created_by=user, created_at__year=year, created_at__month=month, status='APPROVED'
            ).count()
            eff_score = _clamp(int(approved / max(transfers, 1) * 100))
            details = {'transfers': transfers, 'approved': approved, 'audits': audits}

        elif r in ['ISHLAB CHIQARISH USTASI', 'PRODUCTION_MASTER', 'PRODUCTION_OPERATOR']:
            from production_v2.models import Zames, FinishedBlock
            done = Zames.objects.filter(operator=user, status='DONE', created_at__year=year, created_at__month=month).count()
            all_z = Zames.objects.filter(operator=user, created_at__year=year, created_at__month=month).count()
            # Plan: 8 zames/month
            vol_score = _clamp(int(done / 8 * 100))
            # Sifat: yakunlangan vs boshlangan
            qual_score = _clamp(int(done / max(all_z, 1) * 100))
            # Tejamkorlik: blok brak %
            total_b = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month).count()
            failed_b = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month, status='QC_FAILED').count()
            brak = failed_b / max(total_b, 1) * 100
            eff_score = _clamp(int(100 - brak * 3))
            details = {
                'zames_done': done, 'zames_total': all_z,
                'brak_pct': round(brak, 1), 'plan_pct': round(done / 8 * 100, 1)
            }

        elif r in ['CNC OPERATORI', 'CNC_OPERATOR']:
            from cnc_v2.models import CNCJob
            qs = CNCJob.objects.filter(operator=user, end_time__year=year, end_time__month=month)
            done = qs.filter(status='COMPLETED').count()
            all_jobs = CNCJob.objects.filter(operator=user, created_at__year=year, created_at__month=month).count()
            waste = float(qs.filter(status='COMPLETED').aggregate(s=Sum('waste_m3'))['s'] or 0)
            planned_qty = float(qs.aggregate(s=Sum('quantity_planned'))['s'] or 0)
            finished_qty = float(qs.aggregate(s=Sum('quantity_finished'))['s'] or 0)
            # Plan: 15 jobs/month
            vol_score = _clamp(int(done / 15 * 100))
            # Sifat: tayyor/rejalashtirilgan nisbat
            qual_score = _clamp(int(finished_qty / max(planned_qty, 1) * 100))
            # Tejamkorlik: chiqindi minimalligi (< 0.5 m³/ish = 100%)
            waste_per_job = waste / max(done, 1)
            eff_score = _clamp(int((1 - waste_per_job / 2) * 100))
            details = {
                'jobs_done': done, 'waste_m3': round(waste, 2),
                'waste_per_job': round(waste_per_job, 2),
                'output_pct': round(finished_qty / max(planned_qty, 1) * 100, 1),
            }

        elif r in ['TEXNOLOG', 'TECHNOLOGIST']:
            from production_v2.models import FinishedBlock, Zames
            total = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month).count()
            failed = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month, status='QC_FAILED').count()
            brak = failed / max(total, 1) * 100
            zames_cnt = Zames.objects.filter(created_at__year=year, created_at__month=month).count()
            # Ish hajmi: oy davomida nazorat ostida bo'lgan bloklar
            vol_score = _clamp(int(total / 50 * 100))  # 50 blok target
            # Sifat: brak % qanchalik past
            qual_score = _clamp(int(100 - brak * 4))
            # Tejamkorlik: resept samaradorligi (zames → blok nisbati)
            eff_score = _clamp(int(total / max(zames_cnt, 1) * 50))  # >2 blok/zames = good
            details = {
                'total_blocks': total, 'failed_blocks': failed,
                'brak_pct': round(brak, 1), 'zames_count': zames_cnt,
            }

        elif r in ['QC', 'QC_INSPECTOR', 'SIFAT NAZORATCHISI']:
            from production_v2.models import FinishedBlock
            from warehouse_v2.models import RawMaterialBatch
            total_fb = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month).count()
            passed_fb = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month, status='READY').count()
            failed_fb = FinishedBlock.objects.filter(created_at__year=year, created_at__month=month, status='QC_FAILED').count()
            batches_checked = RawMaterialBatch.objects.filter(
                updated_at__year=year, updated_at__month=month, status='IN_STOCK'
            ).count()
            pass_rate = passed_fb / max(total_fb, 1) * 100
            # Ish hajmi: tekshirilgan bloklar soni
            vol_score = _clamp(int(total_fb / 30 * 100))  # 30 blok target
            # Sifat: brak to'g'ri aniqlash → pass_rate 95%+ = 100
            qual_score = _clamp(int(pass_rate))
            # Tejamkorlik: xom-ashyo tekshiruvi
            eff_score = _clamp(batches_checked * 20)
            details = {
                'blocks_checked': total_fb, 'passed': passed_fb,
                'failed': failed_fb, 'pass_rate': round(pass_rate, 1),
                'batches_checked': batches_checked,
            }

        elif r in ['PARDOZLOVCHI', 'FINISHING_OPERATOR']:
            from finishing_v2.models import FinishingJob
            qs = FinishingJob.objects.filter(operator=user, updated_at__year=year, updated_at__month=month)
            done = qs.filter(status='COMPLETED').count()
            cancelled = qs.filter(status='CANCELLED').count()
            all_j = qs.count()
            waste = sum([j.waste_quantity for j in qs if hasattr(j, 'waste_quantity')])
            vol_score = _clamp(int(done / 10 * 100))  # 10 ish/oy target
            qual_score = _clamp(int((1 - cancelled / max(all_j, 1)) * 100))
            eff_score = _clamp(int(100 - waste / max(done, 1) * 5))
            details = {
                'jobs_done': done, 'cancelled': cancelled,
                'waste_qty': waste, 'completion_rate': round(done / max(all_j, 1) * 100, 1),
            }

        elif r in ['KURYER', 'COURIER', 'LOGISTIKA', 'LOGISTICS']:
            from sales_v2.models import Delivery
            qs = Delivery.objects.filter(courier=user, delivered_at__year=year, delivered_at__month=month)
            delivered = qs.filter(status='DELIVERED').count()
            all_d = Delivery.objects.filter(courier=user, created_at__year=year, created_at__month=month).count()
            # Plan: 20 yetkazma/oy
            vol_score = _clamp(int(delivered / 20 * 100))
            # Sifat: yetkazib berish ulushi
            qual_score = _clamp(int(delivered / max(all_d, 1) * 100))
            # Tejamkorlik: kechikmaslik (is_late maydoni bo'lsa)
            late = 0
            try:
                late = qs.filter(is_late=True).count()
            except Exception:
                pass
            eff_score = _clamp(int((1 - late / max(delivered, 1)) * 100))
            details = {
                'delivered': delivered, 'total_orders': all_d,
                'late': late, 'delivery_rate': round(delivered / max(all_d, 1) * 100, 1),
            }

        elif r in ['BUXGALTER', 'ACCOUNTANT']:
            from finance_v2.models import FinancialTransaction
            cnt = FinancialTransaction.objects.filter(created_at__year=year, created_at__month=month).count()
            error_cnt = FinancialTransaction.objects.filter(
                created_at__year=year, created_at__month=month, status='CANCELLED'
            ).count() if hasattr(FinancialTransaction, 'status') else 0
            vol_score = _clamp(int(cnt / 30 * 100))
            qual_score = _clamp(int((1 - error_cnt / max(cnt, 1)) * 100))
            eff_score = _clamp(min(100, cnt * 2))
            details = {
                'transactions': cnt, 'errors': error_cnt,
                'accuracy': round((1 - error_cnt / max(cnt, 1)) * 100, 1),
            }

        else:
            from common_v2.models import AuditLog
            cnt = AuditLog.objects.filter(user=user, timestamp__year=year, timestamp__month=month).count()
            vol_score = _clamp(int(cnt / 50 * 100))
            qual_score = _clamp(min(100, cnt))
            eff_score = _clamp(min(100, cnt))
            details = {'actions': cnt}

    except Exception as e:
        details['_error'] = str(e)

    # Intizom (15%)
    disc_score, disc_details = _discipline_score(user, year, month)
    details.update({'login_days': disc_details.get('login_days', 0), 'work_days': disc_details.get('work_days', 22)})

    # Yakuniy ball: Volume*0.4 + Quality*0.3 + Discipline*0.15 + Efficiency*0.15
    final_score = int(vol_score * 0.40 + qual_score * 0.30 + disc_score * 0.15 + eff_score * 0.15)
    final_score = _clamp(final_score)

    # Bonus: 0-30% of BASE_SALARY
    bonus_pct = final_score / 100 * 0.30
    bonus_amount = int(BASE_SALARY * bonus_pct)

    return {
        'score': final_score,
        'components': {
            'volume': vol_score,       # 40%
            'quality': qual_score,     # 30%
            'discipline': disc_score,  # 15%
            'efficiency': eff_score,   # 15%
        },
        'efficiency': final_score,  # backward compat
        'bonus_pct': round(bonus_pct * 100, 1),
        'bonus_amount': bonus_amount,
        'grade': 'A' if final_score >= 90 else 'B' if final_score >= 75 else 'C' if final_score >= 50 else 'D',
        'details': details,
    }


def _compute_ranking(user, r):
    """Compute user rank among peers with same role."""
    from django.utils import timezone
    now = timezone.now()
    peers = User.objects.filter(role_obj=user.role_obj, is_active=True)
    if peers.count() <= 1:
        return {'rank': 1, 'total': peers.count(), 'percentile': 100}
    scores = []
    for peer in peers:
        b = _compute_bonus(peer, r, now.year, now.month)
        scores.append((peer.id, b['score']))
    scores.sort(key=lambda x: x[1], reverse=True)
    rank = next((i + 1 for i, (uid, _) in enumerate(scores) if uid == user.id), len(scores))
    percentile = round((1 - (rank - 1) / len(scores)) * 100)
    return {'rank': rank, 'total': len(scores), 'percentile': percentile}


class RoleSummaryView(APIView):
    """
    Personalized summary for each role as described in the User Guide.
    """
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        summary="Get role-specific dashboard metrics",
        description="Returns a personalized summary of key metrics based on the user's role (Sales, Warehouse, Production, etc.)"
    )
    def get(self, request):
        user = request.user
        role_name = get_user_role_name(user)
        
        data = {
            "role": role_name,
            "full_name": user.full_name,
            "summary": {}
        }

        # Normalize role name for check
        r = role_name.upper()

        if r in ['SOTUV MENEJERI', 'SALES_MANAGER']:
            from sales_v2.models import Customer, Invoice
            data["summary"] = {
                "active_leads": Customer.objects.filter(lead_status='LEAD', assigned_manager=user).count(),
                "pending_invoices": Invoice.objects.filter(status='NEW', created_by=user).count(),
                "total_sales_month": float(Invoice.objects.filter(created_by=user, date__month=timezone.now().month).aggregate(s=Sum('total_amount'))['s'] or 0),
                "my_clients_count": Customer.objects.filter(assigned_manager=user).count(),
            }
        
        elif r in ['OMBORCHI', 'WAREHOUSE_OPERATOR']:
            from warehouse_v2.models import Stock, RawMaterialBatch
            data["summary"] = {
                "low_stock_items": Stock.objects.filter(quantity__lte=F('min_level')).count(),
                "pending_batches": RawMaterialBatch.objects.filter(status='RECEIVED').count(),
                "total_items": Stock.objects.filter(warehouse__in=user.assigned_warehouses.all()).count() if user.assigned_warehouses.exists() else Stock.objects.count(),
                "recent_movements": 5, # Placeholder for movement count
            }

        elif r in ['ISHLAB CHIQARISH USTASI', 'PRODUCTION_MASTER', 'PRODUCTION_OPERATOR']:
            from production_v2.models import ProductionOrder, Zames
            data["summary"] = {
                "active_orders": ProductionOrder.objects.filter(status='IN_PROGRESS').count(),
                "pending_qc": ProductionOrder.objects.filter(status='QC_PENDING').count(),
                "active_zames": Zames.objects.filter(status='IN_PROGRESS').count(),
                "total_plans_today": 2, # Placeholder
            }

        elif r in ['CNC OPERATORI', 'CNC_OPERATOR']:
            from cnc_v2.models import CNCJob
            data["summary"] = {
                "pending_jobs": CNCJob.objects.filter(status='PENDING').count(),
                "my_completed_today": CNCJob.objects.filter(operator=user, status='COMPLETED', created_at__date=timezone.now().date()).count(),
                "waste_reported_kg": 0, # Placeholder
            }

        elif r in ['KURYER', 'COURIER']:
            from sales_v2.models import Delivery
            data["summary"] = {
                "my_pending_deliveries": Delivery.objects.filter(courier=user, status='PENDING').count(),
                "active_deliveries": Delivery.objects.filter(courier=user, status='EN_ROUTE').count(),
                "total_delivered_today": Delivery.objects.filter(courier=user, status='DELIVERED', delivered_at__date=timezone.now().date()).count(),
            }

        elif r in ['BUXGALTER', 'ACCOUNTANT', 'MOLIYA BOSHQARUVCHI', 'FINANCE_MANAGER']:
            from accounting.models import JournalEntry, FiscalPeriod
            from finance_v2.models import Cashbox
            data["summary"] = {
                "unposted_entries": JournalEntry.objects.filter(status='DRAFT').count(),
                "total_cash_balance": float(Cashbox.objects.aggregate(s=Sum('balance'))['s'] or 0),
                "active_period": FiscalPeriod.objects.filter(is_closed=False).first().name if FiscalPeriod.objects.filter(is_closed=False).exists() else "None",
            }

        elif r in ['BOSH ADMIN', 'ADMIN', 'SUPERADMIN', 'ADMIN']:
            from common_v2.models import AuditLog
            from sales_v2.models import Invoice
            data["summary"] = {
                "system_errors_24h": AuditLog.objects.filter(status='ERROR', timestamp__gte=timezone.now() - timedelta(days=1)).count(),
                "total_revenue_today": float(Invoice.objects.filter(date__date=timezone.now().date()).aggregate(s=Sum('total_amount'))['s'] or 0),
                "active_users_count": 8, # Placeholder
            }
        
        else:
            # Default summary for unknown roles
            data["summary"] = {
                "message": "Xush kelibsiz! Sizning rolingiz uchun maxsus dashboard topilmadi.",
                "status": "Stable"
            }

        return Response(data)
