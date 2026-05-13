from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse
from django.db.models import Sum, Count, Avg, Q, F
from django.utils import timezone
from datetime import timedelta
from .models import Customer, Invoice, SaleItem, ContactLog, Delivery, Contract, NotificationLog
from .serializers import (
    CustomerSerializer, InvoiceSerializer, SaleItemSerializer, 
    ContactLogSerializer, DeliverySerializer, CourierAssignSerializer,
    ContractSerializer, NotificationLogSerializer
)
from .services import create_invoice, transition_invoice_status, create_contact_log, create_production_order_from_sale
from accounts.permissions import IsAdminOrSalesManager, IsAdminOrCourier, IsAdmin, get_user_role_name
from common_v2.mixins import NoDeleteMixin
from reports_v2.services import build_export_response_content

class CustomerViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer

    def get_permissions(self):
        return [IsAdminOrSalesManager()]

    @action(detail=True, methods=['post'], url_path='add-contact-log')
    def add_contact_log(self, request, pk=None):
        try:
            log = create_contact_log(
                customer_id=pk,
                manager=request.user,
                contact_type=request.data.get('contact_type'),
                notes=request.data.get('notes'),
                follow_up_date=request.data.get('follow_up_date')
            )
            return Response(ContactLogSerializer(log).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['get'], url_path='contact-logs')
    def get_contact_logs(self, request, pk=None):
        logs = ContactLog.objects.filter(customer_id=pk).order_by('-created_at')
        return Response(ContactLogSerializer(logs, many=True).data)

class InvoiceViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    queryset = Invoice.objects.all().order_by('-date')
    serializer_class = InvoiceSerializer
    filterset_fields = ['customer', 'status', 'payment_method']

    def get_permissions(self):
        return [IsAdminOrSalesManager()]

    @action(detail=False, methods=['post'], url_path='create-invoice')
    def create_invoice_action(self, request):
        warehouse_id = request.data.get('warehouse_id')
        customer_id = request.data.get('customer_id')
        items = request.data.get('items')
        payment_method = request.data.get('payment_method', 'CASH')
        delivery_address = request.data.get('delivery_address', '')
        notes = request.data.get('notes', '')
        discount_amount = request.data.get('discount_amount', 0)
        
        if not all([warehouse_id, customer_id, items]):
            return Response({"error": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invoice = create_invoice(
                warehouse_id=warehouse_id,
                customer_id=customer_id,
                items=items,
                payment_method=payment_method,
                delivery_address=delivery_address,
                notes=notes,
                discount_amount=discount_amount,
                created_by=request.user
            )
            return Response(self.get_serializer(invoice).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='transition-status')
    def transition_status(self, request, pk=None):
        new_status = request.data.get('status')
        if not new_status:
            return Response({"error": "Status is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            invoice = transition_invoice_status(pk, new_status, performed_by=request.user)
            return Response(self.get_serializer(invoice).data)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], url_path='assign-courier')
    def assign_courier(self, request, pk=None):
        invoice = self.get_object()
        courier_id = request.data.get('courier_id')
        if not courier_id:
            return Response({'error': 'courier_id is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        delivery, created = Delivery.objects.get_or_create(invoice=invoice)
        delivery.courier_id = courier_id
        delivery.status = 'PENDING'
        delivery.save()
        
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=['post'], url_path='generate-waybill')
    def generate_waybill(self, request, pk=None):
        """Generate a waybill (nakladnoy) document for a shipped invoice."""
        invoice = self.get_object()
        if invoice.status not in ('SHIPPED', 'CONFIRMED', 'COMPLETED'):
            return Response({"error": "Buyurtma hali jo'natilmagan"}, status=status.HTTP_400_BAD_REQUEST)
        
        from documents.models import Document
        waybill_number = f"WB-{invoice.invoice_number}"
        doc, created = Document.objects.get_or_create(
            type='ICHKI_YUK_XATI',
            number=waybill_number,
            defaults={
                'created_by': request.user,
                'status': 'CREATED',
                'client': invoice.customer,
            }
        )
        return Response({
            "document_id": doc.id,
            "document_number": str(doc.id),
            "invoice_number": invoice.invoice_number,
            "customer": invoice.customer.name,
            "items": [{"product": i.product.name, "quantity": i.quantity, "price": float(i.price)} for i in invoice.items.all()],
            "delivery_address": invoice.delivery_address or "",
            "total": float(invoice.total_amount),
            "created": True if created else False
        })

class SaleItemViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    queryset = SaleItem.objects.all()
    serializer_class = SaleItemSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsAdminOrSalesManager()]
        return [IsAdmin()]

class DeliveryViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    queryset = Delivery.objects.all().select_related('invoice', 'invoice__customer', 'courier').order_by('-id')
    serializer_class = DeliverySerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        user = self.request.user
        role_name = get_user_role_name(user)
        if user.is_superuser or role_name in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN', 'Sotuv menejeri', 'SALES_MANAGER']:
            return queryset
        if role_name in ['Kuryer', 'COURIER']:
            return queryset.filter(courier=user)
        return queryset.none()

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'pickup', 'deliver', 'my_deliveries']:
            return [IsAdminOrCourier()]
        if self.action in ['assign']:
            return [IsAdminOrSalesManager()]
        return [IsAdminOrSalesManager()]

    @action(detail=False, methods=['get'], url_path='my-deliveries')
    def my_deliveries(self, request):
        """Courier sees only their assigned deliveries."""
        deliveries = Delivery.objects.filter(
            courier=request.user
        ).select_related('invoice', 'invoice__customer').order_by('-id')
        return Response(DeliverySerializer(deliveries, many=True).data)

    @action(detail=True, methods=['post'], url_path='pickup')
    def pickup(self, request, pk=None):
        """Courier picks up the order — EN_ROUTE."""
        delivery = self.get_object()
        delivery.status = 'EN_ROUTE'
        delivery.started_at = timezone.now()
        delivery.courier = request.user
        delivery.save()
        
        # Update Invoice status
        invoice = delivery.invoice
        transition_invoice_status(invoice.id, 'EN_ROUTE', performed_by=request.user)
        
        return Response(DeliverySerializer(delivery).data)
        
    @action(detail=True, methods=['post'], url_path='deliver')
    def deliver(self, request, pk=None):
        """Courier delivers the order — DELIVERED → COMPLETED."""
        delivery = self.get_object()
        delivery.status = 'DELIVERED'
        delivery.delivered_at = timezone.now()
        delivery.save()
        
        # Transition Invoice through DELIVERED → COMPLETED
        invoice = delivery.invoice
        transition_invoice_status(invoice.id, 'DELIVERED', performed_by=request.user)
        transition_invoice_status(invoice.id, 'COMPLETED', performed_by=request.user)
        
        # Log notification
        NotificationLog.objects.create(
            event_type='ORDER_SHIPPED',
            message=f"Buyurtma {invoice.invoice_number} yetkazildi — {invoice.customer.name}",
            customer=invoice.customer,
            recipient=request.user,
            is_sent=True,
            sent_via='LOG'
        )
        
        return Response(DeliverySerializer(delivery).data)

    @action(detail=True, methods=['post'], url_path='assign')
    def assign(self, request, pk=None):
        """Admin assigns a courier to a delivery."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        delivery = self.get_object()
        courier_id = request.data.get('courier_id')
        if courier_id:
            delivery.courier = User.objects.get(id=courier_id)
            delivery.save()
        return Response(DeliverySerializer(delivery).data)


class ContractViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    queryset = Contract.objects.all().order_by('-created_at')
    serializer_class = ContractSerializer
    permission_classes = [IsAdminOrSalesManager]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class NotificationLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotificationLog.objects.all().order_by('-created_at')[:100]
    serializer_class = NotificationLogSerializer
    permission_classes = [IsAdminOrSalesManager]


class SalesKPIView(APIView):
    """Sales KPI endpoint for the Sales Manager dashboard."""
    permission_classes = [IsAdminOrSalesManager]

    def get(self, request):
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0)
        
        invoices = Invoice.objects.all()
        month_invoices = invoices.filter(date__gte=month_start)
        
        # Monthly target (placeholder — can be made configurable)
        monthly_target = 100_000_000  # 100M UZS
        monthly_actual = float(month_invoices.aggregate(s=Sum('total_amount'))['s'] or 0)
        
        # Conversion rate: WON leads / total leads
        total_leads = Customer.objects.count()
        won_leads = Customer.objects.filter(lead_status='WON').count()
        conversion = round((won_leads / total_leads * 100), 1) if total_leads else 0
        
        # Average check
        avg_check = float(invoices.aggregate(a=Avg('total_amount'))['a'] or 0)
        
        # Top client
        top_client = Customer.objects.annotate(
            total=Sum('invoices__total_amount')
        ).order_by('-total').first()
        
        # Weekly trend (last 7 days)
        weekly = []
        for i in range(6, -1, -1):
            day = (now - timedelta(days=i)).date()
            day_total = float(invoices.filter(date__date=day).aggregate(s=Sum('total_amount'))['s'] or 0)
            weekly.append({"day": day.strftime("%a"), "value": day_total})
        
        # Today stats
        today_count = invoices.filter(date__date=now.date()).count()
        today_sum = float(invoices.filter(date__date=now.date()).aggregate(s=Sum('total_amount'))['s'] or 0)
        
        return Response({
            "monthly_target": monthly_target,
            "monthly_actual": monthly_actual,
            "monthly_progress": round(monthly_actual / monthly_target * 100, 1) if monthly_target else 0,
            "conversion_rate": conversion,
            "avg_check": round(avg_check, 0),
            "top_client": {"name": top_client.name, "total": float(top_client.total or 0)} if top_client else None,
            "weekly_trend": weekly,
            "today_count": today_count,
            "today_sum": today_sum,
            "active_orders": invoices.filter(status__in=['NEW', 'CONFIRMED']).count(),
            "active_contracts": Contract.objects.filter(status='ACTIVE').count(),
        })


class SalesExportView(APIView):
    permission_classes = [IsAdminOrSalesManager]

    def get(self, request):
        file_format = request.query_params.get('file_format') or request.query_params.get('export_format', 'PDF')
        file_format = file_format.upper()
        period = request.query_params.get('period', 'This Month')
        now = timezone.now()

        if period == 'Today':
            start_date = now.date()
        elif period == 'Last 7 Days':
            start_date = (now - timedelta(days=6)).date()
        else:
            start_date = now.replace(day=1).date()

        invoices = Invoice.objects.filter(date__date__gte=start_date).select_related('customer').order_by('-date')
        rows = [['Invoys', 'Sana', 'Mijoz', 'Holat', 'Tolov', 'Summa']]
        for inv in invoices:
            rows.append([
                inv.invoice_number,
                inv.date.strftime('%Y-%m-%d'),
                inv.customer.name,
                inv.status,
                inv.payment_method,
                float(inv.total_amount),
            ])
        rows.append([])
        rows.append(['Jami', '', '', '', '', float(invoices.aggregate(s=Sum('total_amount'))['s'] or 0)])

        title = f'Sales export - {period}'
        content, extension, content_type = build_export_response_content(title, rows, file_format)
        response = HttpResponse(content, content_type=content_type)
        response['Content-Disposition'] = f'attachment; filename="sales-export.{extension}"'
        return response


class DebtorsView(APIView):
    """Dedicated debtors analysis endpoint."""
    permission_classes = [IsAdminOrSalesManager]

    def get(self, request):
        # Get customers with debt (negative balance = they owe us)
        from finance_v2.models import ClientBalance
        
        debtors = []
        total_debt = 0
        
        for balance in ClientBalance.objects.filter(total_debt__gt=0).select_related('customer'):
            debt_amount = float(balance.total_debt)
            total_debt += debt_amount
            
            # Calculate debt age based on last invoice
            last_invoice = Invoice.objects.filter(
                customer=balance.customer, payment_method='DEBT'
            ).order_by('-date').first()
            
            days_overdue = 0
            if last_invoice:
                days_overdue = (timezone.now() - last_invoice.date).days
            
            aging = '0-30' if days_overdue <= 30 else '30-60' if days_overdue <= 60 else '60-90' if days_overdue <= 90 else '90+'
            
            debtors.append({
                "id": balance.customer.id,
                "name": balance.customer.name,
                "company": balance.customer.company_name or "",
                "phone": balance.customer.phone,
                "debt": debt_amount,
                "days_overdue": days_overdue,
                "aging": aging,
                "last_invoice": last_invoice.invoice_number if last_invoice else None,
            })
        
        # Sort by debt descending
        debtors.sort(key=lambda x: x['debt'], reverse=True)
        
        # Aging summary
        aging_summary = {
            "0-30": sum(d['debt'] for d in debtors if d['aging'] == '0-30'),
            "30-60": sum(d['debt'] for d in debtors if d['aging'] == '30-60'),
            "60-90": sum(d['debt'] for d in debtors if d['aging'] == '60-90'),
            "90+": sum(d['debt'] for d in debtors if d['aging'] == '90+'),
        }
        
        return Response({
            "total_debt": total_debt,
            "debtors_count": len(debtors),
            "avg_debt": round(total_debt / len(debtors), 0) if debtors else 0,
            "top_debtor": debtors[0] if debtors else None,
            "aging_summary": aging_summary,
            "debtors": debtors,
        })
