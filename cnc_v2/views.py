from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CNCJob, WasteProcessing
from .serializers import CNCJobSerializer, WasteProcessingSerializer
from .services import start_cnc_job, pause_cnc_job, finish_cnc_job
from accounts.permissions import IsCNCOperator, get_user_role_name
from django.utils import timezone

class CNCJobViewSet(viewsets.ModelViewSet):
    serializer_class = CNCJobSerializer
    permission_classes = [IsCNCOperator]
    queryset = CNCJob.objects.all()

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser or get_user_role_name(user) in ['Bosh Admin', 'Admin', 'Ishlab chiqarish ustasi', 'SUPERADMIN', 'ADMIN', 'PRODUCTION_OPERATOR']:
            return CNCJob.objects.all().order_by('-priority', '-created_at')
        return CNCJob.objects.filter(operator=user).order_by('-priority', '-created_at')

    def perform_create(self, serializer):
        job_number = f"CNC-{timezone.now().strftime('%y%m%d%H%M%S')}"
        input_finished_block = serializer.validated_data.get('input_finished_block')
        kwargs = {}
        if input_finished_block and not serializer.validated_data.get('input_block'):
            kwargs['input_block'] = input_finished_block.lot
        serializer.save(operator=self.request.user, job_number=job_number, **kwargs)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        job = start_cnc_job(pk, operator=request.user)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        job = pause_cnc_job(pk)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        finished_qty = request.data.get('finished_qty', 0)
        waste_m3 = request.data.get('waste_m3', 0)
        job = finish_cnc_job(pk, finished_qty, waste_m3, operator=request.user)
        return Response(self.get_serializer(job).data)

from django.db.models import Sum
from datetime import timedelta

class WasteProcessingViewSet(viewsets.ModelViewSet):
    queryset = WasteProcessing.objects.all().order_by('-date')
    serializer_class = WasteProcessingSerializer
    permission_classes = [IsCNCOperator]

    def get_queryset(self):
        queryset = super().get_queryset()
        dept = self.request.query_params.get('department')
        reason = self.request.query_params.get('reason')
        if dept:
            queryset = queryset.filter(source_department=dept)
        if reason:
            queryset = queryset.filter(reason=reason)
        return queryset

    def perform_create(self, serializer):
        serializer.save(operator=self.request.user)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        now = timezone.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)

        def get_sum(start_date):
            return WasteProcessing.objects.filter(date__gte=start_date).aggregate(total=Sum('waste_amount_kg'))['total'] or 0

        # Stats by department
        dept_stats = WasteProcessing.objects.filter(date__gte=month_start).values('source_department').annotate(total=Sum('waste_amount_kg'))

        return Response({
            'today': get_sum(today_start),
            'week': get_sum(week_start),
            'month': get_sum(month_start),
            'by_department': dept_stats
        })
