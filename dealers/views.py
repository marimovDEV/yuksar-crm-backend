from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.utils import timezone
from .models import Dealer, DealerPayment, DealerOrder
from .serializers import DealerSerializer, DealerListSerializer, DealerPaymentSerializer, DealerOrderSerializer


class DealerViewSet(viewsets.ModelViewSet):
    queryset = Dealer.objects.all().order_by('-created_at')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return DealerListSerializer
        return DealerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        region = self.request.query_params.get('region')
        category = self.request.query_params.get('category')
        status_param = self.request.query_params.get('status')
        if region:
            qs = qs.filter(region=region)
        if category:
            qs = qs.filter(category=category)
        if status_param:
            qs = qs.filter(status=status_param)
        return qs

    @action(detail=True, methods=['get'])
    def payments(self, request, pk=None):
        dealer = self.get_object()
        payments = DealerPayment.objects.filter(dealer=dealer).order_by('-date')[:20]
        serializer = DealerPaymentSerializer(payments, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def orders(self, request, pk=None):
        dealer = self.get_object()
        serializer = DealerOrderSerializer(data=request.data)
        if serializer.is_valid():
            order = serializer.save(dealer=dealer, created_by=request.user)
            # Update dealer debt
            dealer.debt += order.amount
            dealer.last_order = timezone.now()
            dealer.save(update_fields=['debt', 'last_order'])
            return Response(DealerOrderSerializer(order).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        dealer = self.get_object()
        serializer = DealerPaymentSerializer(data=request.data)
        if serializer.is_valid():
            payment = serializer.save(dealer=dealer, created_by=request.user)
            # Reduce dealer debt
            dealer.debt = max(0, dealer.debt - payment.amount)
            dealer.save(update_fields=['debt'])
            return Response(DealerPaymentSerializer(payment).data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
