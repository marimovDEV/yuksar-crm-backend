from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import (
    Supplier, Material, RawMaterialBatch, Warehouse, Stock, 
    WarehouseTransfer, PurchaseOrder, PurchaseOrderItem
)
from .serializers import (
    SupplierSerializer, MaterialSerializer, RawMaterialBatchSerializer,
    WarehouseSerializer, StockSerializer, WarehouseTransferSerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer
)
from inventory.services import update_inventory
from accounts.permissions import IsAdmin, IsWarehouseOperator, get_user_role_name

class SupplierViewSet(viewsets.ModelViewSet):
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        po = self.get_object()
        po.status = 'APPROVED'
        po.save()
        return Response({'status': 'Tasdiqlandi'})

    @action(detail=True, methods=['post'])
    def order(self, request, pk=None):
        po = self.get_object()
        po.status = 'ORDERED'
        po.save()
        return Response({'status': 'Buyurtma berildi'})

    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        po = self.get_object()
        po.status = 'IN_TRANSIT'
        po.save()
        return Response({'status': 'Yo\'lda'})

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        po = self.get_object()
        if po.status != 'IN_TRANSIT':
            return Response({'error': 'Faqat yo\'ldagi buyurtmalarni qabul qilish mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            po.status = 'RECEIVED'
            po.received_at = timezone.now()
            po.save()

            for item in po.items.all():
                batch_num = f"BAT-{po.po_number}-{item.id}"
                RawMaterialBatch.objects.create(
                    invoice_number=po.po_number,
                    supplier=po.supplier,
                    supplier_name=po.supplier.name,
                    quantity_kg=item.quantity,
                    remaining_quantity=item.quantity,
                    price_per_unit=item.price_per_unit,
                    currency=po.currency,
                    batch_number=batch_num,
                    status='INSPECTION', # Sent to QC Center
                    responsible_user=request.user,
                    material=item.material
                )
        return Response({'status': 'Qabul qilindi va QC navbatiga yuborildi'})

class MaterialViewSet(viewsets.ModelViewSet):
    queryset = Material.objects.all()
    serializer_class = MaterialSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            # All authenticated users can READ materials
            return [permissions.IsAuthenticated()]
        # Only warehouse operators can create/update/delete
        return [IsWarehouseOperator()]

class RawMaterialBatchViewSet(viewsets.ModelViewSet):
    serializer_class = RawMaterialBatchSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.IsAuthenticated()]
        return [IsWarehouseOperator()]

    def get_queryset(self):
        user = self.request.user
        if get_user_role_name(user) in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN'] or user.is_superuser:
            return RawMaterialBatch.objects.all()
        # For operators, show batches they created or those in their assigned warehouses
        return RawMaterialBatch.objects.filter(
            Q(responsible_user=user) | 
            Q(material__stock__warehouse__in=user.assigned_warehouses.all())
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(responsible_user=self.request.user)

    @action(detail=True, methods=['post'])
    def qc_approve(self, request, pk=None):
        batch = self.get_object()
        warehouse_id = request.data.get('warehouse_id')
        if not warehouse_id:
            return Response({'error': 'Ombor tanlanishi shart.'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            warehouse = Warehouse.objects.get(id=warehouse_id)
        except Warehouse.DoesNotExist:
            return Response({'error': 'Tanlangan ombor topilmadi.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            batch.status = 'IN_STOCK'
            batch.save()
            
            # Update inventory
            update_inventory(
                product=batch.material,
                warehouse=warehouse,
                qty=batch.quantity_kg,
                user=request.user,
                reference=f"QC-APP-{batch.batch_number}"
            )
            
        return Response({'status': 'Tasdiqlandi va omborga qo\'shildi'})

    @action(detail=True, methods=['post'])
    def qc_reject(self, request, pk=None):
        batch = self.get_object()
        batch.status = 'CANCELLED'
        batch.save()
        return Response({'status': 'Rad etildi'})

    @action(detail=False, methods=['get'], url_path='by-qr/(?P<qr_code>[^/.]+)')

    def by_qr(self, request, qr_code=None):
        try:
            batch = RawMaterialBatch.objects.get(qr_code=qr_code)
            serializer = self.get_serializer(batch)
            return Response(serializer.data)
        except RawMaterialBatch.DoesNotExist:
            return Response({'error': 'Partiya topilmadi'}, status=status.HTTP_404_NOT_FOUND)

class WarehouseViewSet(viewsets.ModelViewSet):
    serializer_class = WarehouseSerializer
    filterset_fields = ['name']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            # All authenticated users can see warehouses
            return [permissions.IsAuthenticated()]
        # Only warehouse operators can create/update/delete
        return [IsWarehouseOperator()]

    def get_queryset(self):
        user = self.request.user
        if get_user_role_name(user) in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN'] or user.is_superuser:
            return Warehouse.objects.all()
        return user.assigned_warehouses.all()

class StockViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockSerializer
    filterset_fields = {
        'warehouse': ['exact'],
        'warehouse_id': ['exact'],
        'warehouse__name': ['exact', 'icontains'],
        'material': ['exact'],
        'material_id': ['exact'],
        'material__name': ['icontains', 'exact'],
    }

    def get_permissions(self):
        # All authenticated users can view stock levels
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if get_user_role_name(user) in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN'] or user.is_superuser:
            return Stock.objects.all().select_related('warehouse', 'material')
        return Stock.objects.filter(warehouse__in=user.assigned_warehouses.all()).select_related('warehouse', 'material')

class WarehouseTransferViewSet(viewsets.ModelViewSet):
    serializer_class = WarehouseTransferSerializer
    permission_classes = [IsWarehouseOperator]

    def get_queryset(self):
        user = self.request.user
        if get_user_role_name(user) in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN'] or user.is_superuser:
            return WarehouseTransfer.objects.all()
        return WarehouseTransfer.objects.filter(
            Q(from_warehouse__in=user.assigned_warehouses.all()) |
            Q(to_warehouse__in=user.assigned_warehouses.all())
        ).distinct()

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user, status='PENDING')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'PENDING':
            return Response({'error': 'Faqat kutilayotgan o\'tkazmalarni tasdiqlash mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        transfer.status = 'APPROVED'
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.save()
        return Response({'status': 'Tasdiqlandi'})

    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'APPROVED':
            return Response({'error': 'Faqat tasdiqlangan o\'tkazmalarni jo\'natish mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            transfer.status = 'SHIPPED'
            transfer.shipped_by = request.user
            transfer.shipped_at = timezone.now()
            transfer.save()
            
            # Decrease from source warehouse
            update_inventory(
                product=transfer.material,
                warehouse=transfer.from_warehouse,
                qty=-transfer.quantity,
                user=request.user,
                reference=f"SHIP-{transfer.transfer_number}"
            )
            
        return Response({'status': 'Jo\'natildi'})

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'SHIPPED':
            return Response({'error': 'Faqat yo\'ldagi o\'tkazmalarni qabul qilish mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            transfer.status = 'RECEIVED'
            transfer.received_by = request.user
            transfer.received_at = timezone.now()
            transfer.save()
            
            # Increase in destination warehouse
            update_inventory(
                product=transfer.material,
                warehouse=transfer.to_warehouse,
                qty=transfer.quantity,
                user=request.user,
                reference=f"RECV-{transfer.transfer_number}"
            )
            
        return Response({'status': 'Qabul qilindi'})
