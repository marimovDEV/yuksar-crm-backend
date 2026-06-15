from django.db.models import Q
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import transaction
from django.utils import timezone
from .models import (
    Supplier, Material, RawMaterialBatch, Warehouse, Stock, 
    WarehouseTransfer, PurchaseOrder, PurchaseOrderItem, InventoryAudit, InventoryAuditLine
)
from .serializers import (
    SupplierSerializer, MaterialSerializer, RawMaterialBatchSerializer,
    WarehouseSerializer, StockSerializer, WarehouseTransferSerializer,
    PurchaseOrderSerializer, PurchaseOrderItemSerializer,
    InventoryAuditSerializer
)
from inventory.services import update_inventory
from accounts.permissions import (
    IsAdmin, IsWarehouseOperator, IsProductionRelated,
    IsAdminOrDirectorOrAccountant, IsAdminOrDirector, get_user_role_name
)
from common_v2.services import log_action
from transactions.models import Transaction
from production_v2.services import update_block_location, transition_block_status


def _transfer_status_snapshot(transfer):
    return {
        'id': transfer.id,
        'transfer_number': transfer.transfer_number,
        'status': transfer.status,
        'from_warehouse': transfer.from_warehouse_id,
        'to_warehouse': transfer.to_warehouse_id,
        'material': transfer.material_id,
        'batch': transfer.batch_id,
        'quantity': float(transfer.quantity),
        'reason': transfer.reason,
        'notes': transfer.notes,
    }


def _create_transfer_log(user, transfer, description, old_value=None):
    log_action(
        user=user,
        action='TRANSFER',
        module='WAREHOUSE_TRANSFER',
        description=description,
        object_id=transfer.transfer_number,
        old_value=old_value,
        new_value=_transfer_status_snapshot(transfer),
        model_name='WarehouseTransfer',
    )


def _resolve_block_transfer_status(transfer):
    destination_name = (transfer.to_warehouse.name if transfer.to_warehouse else '').lower()
    transfer_type = transfer.transfer_type
    if 'cnc' in destination_name:
        return 'CUTTING'
    if 'finish' in destination_name or 'dekor' in destination_name:
        return 'FINISHING'
    if '4' in destination_name or 'shipment' in destination_name or 'otgruz' in destination_name:
        return 'PACKAGED'
    if transfer_type == WarehouseTransfer.TransferType.WASTE:
        return 'RECYCLE'
    return 'READY'

class SupplierViewSet(viewsets.ModelViewSet):
    """Ta'minotchilar — faqat omborchi va admin."""
    queryset = Supplier.objects.all()
    serializer_class = SupplierSerializer
    permission_classes = [IsWarehouseOperator]

class PurchaseOrderViewSet(viewsets.ModelViewSet):
    """Xarid buyurtmalari — faqat omborchi va admin."""
    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderSerializer
    permission_classes = [IsWarehouseOperator]

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
            # Warehouse, production, technologist, QC, director, accounting can read materials
            return [IsWarehouseOperator() | IsProductionRelated() | IsAdminOrDirectorOrAccountant()]
        # Only warehouse operators can create/update/delete
        return [IsWarehouseOperator()]

class RawMaterialBatchViewSet(viewsets.ModelViewSet):
    serializer_class = RawMaterialBatchSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve', 'by_qr']:
            return [IsWarehouseOperator() | IsProductionRelated() | IsAdminOrDirectorOrAccountant()]
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
            # All operational roles need to see warehouse names (for transfers, forms, etc.)
            return [IsWarehouseOperator() | IsProductionRelated() | IsAdminOrDirectorOrAccountant()]
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
        # Warehouse, production, director, accounting can view stock levels
        # Sales, logistics, CNC, finishing do NOT need raw stock data
        return [IsWarehouseOperator() | IsProductionRelated() | IsAdminOrDirectorOrAccountant()]

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
        requested_status = self.request.data.get('status', WarehouseTransfer.Status.PENDING)
        allowed_status = requested_status if requested_status in [WarehouseTransfer.Status.DRAFT, WarehouseTransfer.Status.PENDING] else WarehouseTransfer.Status.PENDING
        transfer = serializer.save(created_by=self.request.user, status=allowed_status)
        if transfer.block:
            update_block_location(
                transfer.block,
                warehouse=transfer.from_warehouse,
                notes=f"Transfer yaratildi: {transfer.transfer_number}",
                user=self.request.user,
            )
        _create_transfer_log(
            self.request.user,
            transfer,
            f"O‘tkazma yaratildi: {transfer.from_warehouse.name} -> {transfer.to_warehouse.name}",
        )

    @action(detail=True, methods=['post'])
    def submit(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != WarehouseTransfer.Status.DRAFT:
            return Response({'error': 'Faqat qoralama o‘tkazmalarni yuborish mumkin.'}, status=status.HTTP_400_BAD_REQUEST)

        old_value = _transfer_status_snapshot(transfer)
        transfer.status = WarehouseTransfer.Status.PENDING
        transfer.save(update_fields=['status'])
        _create_transfer_log(request.user, transfer, "O‘tkazma tasdiqlashga yuborildi", old_value=old_value)
        return Response({'status': 'Tasdiqlashga yuborildi'})

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'PENDING':
            return Response({'error': 'Faqat kutilayotgan o\'tkazmalarni tasdiqlash mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        old_value = _transfer_status_snapshot(transfer)
        transfer.status = 'APPROVED'
        transfer.approved_by = request.user
        transfer.approved_at = timezone.now()
        transfer.save()
        _create_transfer_log(request.user, transfer, "O‘tkazma tasdiqlandi", old_value=old_value)
        return Response({'status': 'Tasdiqlandi'})

    @action(detail=True, methods=['post'])
    def ship(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != 'APPROVED':
            return Response({'error': 'Faqat tasdiqlangan o\'tkazmalarni jo\'natish mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        old_value = _transfer_status_snapshot(transfer)
        with transaction.atomic():
            transfer.status = WarehouseTransfer.Status.IN_TRANSIT
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

            Transaction.objects.create(
                product=transfer.material,
                block=transfer.block,
                from_warehouse=transfer.from_warehouse,
                to_warehouse=transfer.to_warehouse,
                from_location_name=transfer.from_warehouse.name,
                to_location_name=transfer.to_warehouse.name,
                quantity=float(transfer.quantity),
                type='TRANSFER',
                batch=transfer.batch,
                batch_number=transfer.batch.batch_number if transfer.batch else None,
                user=request.user,
                notes=f"{transfer.transfer_number}: jo'natildi",
            )

            if transfer.block:
                transition_block_status(
                    transfer.block,
                    'TRANSFERRED',
                    user=request.user,
                    notes=f"{transfer.transfer_number}: {transfer.from_warehouse.name} dan jo'natildi",
                )

        _create_transfer_log(request.user, transfer, "O‘tkazma yo‘lga chiqarildi", old_value=old_value)
            
        return Response({'status': 'Jo\'natildi'})

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status not in [WarehouseTransfer.Status.IN_TRANSIT, WarehouseTransfer.Status.SHIPPED]:
            return Response({'error': 'Faqat yo\'ldagi o\'tkazmalarni qabul qilish mumkin.'}, status=status.HTTP_400_BAD_REQUEST)
        
        old_value = _transfer_status_snapshot(transfer)
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

            if transfer.block:
                next_status = _resolve_block_transfer_status(transfer)
                update_block_location(
                    transfer.block,
                    warehouse=transfer.to_warehouse,
                    zone=request.data.get('zone', transfer.block.zone),
                    rack=request.data.get('rack', transfer.block.rack),
                    notes=f"{transfer.transfer_number}: {transfer.to_warehouse.name} ga qabul qilindi",
                    user=request.user,
                )
                transition_block_status(
                    transfer.block,
                    next_status,
                    user=request.user,
                    notes=f"{transfer.transfer_number}: yangi holat {next_status}",
                )

        _create_transfer_log(request.user, transfer, "O‘tkazma qabul qilindi", old_value=old_value)
            
        return Response({'status': 'Qabul qilindi'})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status != WarehouseTransfer.Status.RECEIVED:
            return Response({'error': 'Faqat qabul qilingan o‘tkazmalarni yakunlash mumkin.'}, status=status.HTTP_400_BAD_REQUEST)

        old_value = _transfer_status_snapshot(transfer)
        transfer.status = WarehouseTransfer.Status.COMPLETED
        if request.data.get('notes'):
            transfer.notes = request.data['notes']
        transfer.save(update_fields=['status', 'notes'])
        if transfer.block:
            transition_block_status(
                transfer.block,
                _resolve_block_transfer_status(transfer),
                user=request.user,
                notes=f"{transfer.transfer_number}: transfer yakunlandi",
            )
        _create_transfer_log(request.user, transfer, "O‘tkazma to‘liq yakunlandi", old_value=old_value)
        return Response({'status': 'Yakunlandi'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        transfer = self.get_object()
        if transfer.status in [WarehouseTransfer.Status.RECEIVED, WarehouseTransfer.Status.COMPLETED]:
            return Response({'error': 'Qabul qilingan yoki yakunlangan o‘tkazmani bekor qilib bo‘lmaydi.'}, status=status.HTTP_400_BAD_REQUEST)

        old_value = _transfer_status_snapshot(transfer)
        transfer.status = WarehouseTransfer.Status.CANCELLED
        if request.data.get('notes'):
            transfer.notes = request.data['notes']
        transfer.save(update_fields=['status', 'notes'])
        _create_transfer_log(request.user, transfer, "O‘tkazma bekor qilindi", old_value=old_value)
        return Response({'status': 'Bekor qilindi'})


class InventoryAuditViewSet(viewsets.ModelViewSet):
    serializer_class = InventoryAuditSerializer
    permission_classes = [IsWarehouseOperator]

    def get_queryset(self):
        user = self.request.user
        queryset = InventoryAudit.objects.all().select_related(
            'warehouse', 'auditor', 'approved_by'
        ).prefetch_related('lines__material').order_by('-created_at')
        if get_user_role_name(user) in ['Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN'] or user.is_superuser:
            return queryset
        return queryset.filter(warehouse__in=user.assigned_warehouses.all())

    def perform_create(self, serializer):
        with transaction.atomic():
            audit = serializer.save(auditor=self.request.user)
            stocks = Stock.objects.filter(warehouse=audit.warehouse).select_related('material')
            for stock in stocks:
                InventoryAuditLine.objects.create(
                    audit=audit,
                    material=stock.material,
                    system_qty=stock.quantity,
                )

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        audit = self.get_object()
        if audit.status == 'COMPLETED':
            return Response({'error': 'Yakunlangan auditni qayta boshlash mumkin emas.'}, status=status.HTTP_400_BAD_REQUEST)
        audit.status = 'IN_PROGRESS'
        audit.save(update_fields=['status'])
        return Response(self.get_serializer(audit).data)

    @action(detail=True, methods=['post'])
    def count_line(self, request, pk=None):
        audit = self.get_object()
        line_id = request.data.get('line_id')
        actual_qty = request.data.get('actual_qty')
        if line_id is None or actual_qty is None:
            return Response({'error': 'line_id va actual_qty majburiy.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            line = audit.lines.get(id=line_id)
        except InventoryAuditLine.DoesNotExist:
            return Response({'error': 'Audit qatori topilmadi.'}, status=status.HTTP_404_NOT_FOUND)

        line.actual_qty = actual_qty
        line.save(update_fields=['actual_qty'])

        if audit.status == 'DRAFT':
            audit.status = 'IN_PROGRESS'
            audit.save(update_fields=['status'])

        audit.refresh_from_db()
        return Response(self.get_serializer(audit).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        audit = self.get_object()
        if audit.lines.filter(actual_qty__isnull=True).exists():
            return Response({'error': 'Barcha qatorlar bo‘yicha sanalgan miqdor kiritilishi kerak.'}, status=status.HTTP_400_BAD_REQUEST)

        audit.status = 'COMPLETED'
        audit.approved_by = request.user
        audit.remarks = request.data.get('remarks', audit.remarks)
        audit.save(update_fields=['status', 'approved_by', 'remarks'])
        return Response(self.get_serializer(audit).data)
