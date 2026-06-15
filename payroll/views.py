from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from accounts.permissions import IsAdmin, IsAccountant
from .models import PayrollRecord
from .serializers import PayrollSerializer


class PayrollViewSet(viewsets.ModelViewSet):
    queryset = PayrollRecord.objects.select_related('employee').all()
    serializer_class = PayrollSerializer
    permission_classes = [IsAdmin | IsAccountant]

    def get_queryset(self):
        qs = super().get_queryset()
        month = self.request.query_params.get('month')
        emp_id = self.request.query_params.get('employee')
        status_param = self.request.query_params.get('status')
        if month:
            qs = qs.filter(month=month)
        if emp_id:
            qs = qs.filter(employee_id=emp_id)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=True, methods=['post'])
    def pay(self, request, pk=None):
        record = self.get_object()
        if record.status == 'PAID':
            return Response({'detail': 'Already paid'}, status=status.HTTP_400_BAD_REQUEST)
        record.status = 'PAID'
        record.paid_at = timezone.now()
        record.paid_by = request.user
        record.save(update_fields=['status', 'paid_at', 'paid_by'])
        return Response(PayrollSerializer(record).data)

    @action(detail=False, methods=['post'])
    def pay_all(self, request):
        month = request.data.get('month')
        if not month:
            return Response({'detail': 'month required'}, status=status.HTTP_400_BAD_REQUEST)
        records = PayrollRecord.objects.filter(month=month, status='PENDING')
        count = records.update(
            status='PAID',
            paid_at=timezone.now(),
            paid_by=request.user
        )
        return Response({'paid_count': count, 'month': month})

    @action(detail=False, methods=['get'])
    def summary(self, request):
        month = request.query_params.get('month')
        qs = self.get_queryset()
        if month:
            qs = qs.filter(month=month)
        from django.db.models import Sum, Count
        data = qs.aggregate(
            total_fund=Sum('total'),
            paid_count=Count('id', filter=__import__('django.db.models', fromlist=['Q']).Q(status='PAID')),
            pending_count=Count('id', filter=__import__('django.db.models', fromlist=['Q']).Q(status='PENDING')),
        )
        return Response(data)
