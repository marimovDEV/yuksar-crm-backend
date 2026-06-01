from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db.models import Q
from .models import Document
from .serializers import DocumentSerializer
from .services import (
    complete_document, confirm_document, cancel_document,
    assign_courier, start_delivery, confirm_delivery,
    update_document
)
from warehouse_v2.serializers import RawMaterialBatchSerializer
from common_v2.mixins import NoDeleteMixin
from accounts.permissions import IsDocumentOperator, get_user_role_name

class DocumentViewSet(NoDeleteMixin, viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by('-created_at')
    serializer_class = DocumentSerializer
    permission_classes = [IsDocumentOperator]
    filterset_fields = ['type', 'status', 'from_warehouse', 'to_warehouse', 'client']
    search_fields = ['number', 'created_by__username', 'supplier_name']

    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'from_warehouse',
            'to_warehouse',
            'client',
            'delivery__courier',
        )
        role_name = get_user_role_name(self.request.user)
        if role_name in ['Kuryer', 'COURIER'] and not self.request.user.is_superuser:
            queryset = queryset.filter(delivery__courier=self.request.user)
        params = self.request.query_params

        courier_id = params.get('courier_id')
        if courier_id:
            queryset = queryset.filter(delivery__courier_id=courier_id)

        qr_code = params.get('qr_code')
        if qr_code:
            if qr_code.startswith('DOC:'):
                queryset = queryset.filter(number=qr_code.split(':', 1)[1])
            else:
                queryset = queryset.filter(qr_code=qr_code)

        from_warehouse = params.get('from_warehouse')
        to_warehouse = params.get('to_warehouse')
        if from_warehouse and to_warehouse and from_warehouse == to_warehouse:
            queryset = queryset.filter(
                Q(from_warehouse_id=from_warehouse) | Q(to_warehouse_id=to_warehouse)
            )

        return queryset

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)
        # All documents start in 'CREATED' (Draft) by default in our new workflow

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        update_document(instance, request.data, user=request.user)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def partial_update(self, request, *args, **kwargs):
        return self.update(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def receive(self, request, pk=None):
        doc = self.get_object()
        from .services import finish_transfer_inventory
        finish_transfer_inventory(doc, user=request.user)
        return Response({'status': 'received'})

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        doc = self.get_object()
        confirm_document(doc, user=request.user)
        return Response({'status': 'confirmed'})

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        doc = self.get_object()
        cancel_document(doc, user=request.user)
        return Response({'status': 'cancelled'})

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        doc = self.get_object()
        complete_document(doc, user=request.user)
        return Response({'status': 'done'})

    @action(detail=True, methods=['post'])
    def assign_courier(self, request, pk=None):
        doc = self.get_object()
        courier_id = request.data.get('courier_id')
        if not courier_id:
            return Response({'error': 'courier_id is required'}, status=400)
        from django.contrib.auth import get_user_model
        User = get_user_model()
        try:
            courier = User.objects.get(id=courier_id)
            assign_courier(doc, courier)
            return Response({'status': 'courier assigned'})
        except User.DoesNotExist:
            return Response({'error': 'Courier not found'}, status=404)

    @action(detail=True, methods=['post'])
    def start_delivery(self, request, pk=None):
        doc = self.get_object()
        start_delivery(doc, user=request.user)
        return Response({'status': 'delivery started'})

    @action(detail=True, methods=['post'])
    def confirm_delivery(self, request, pk=None):
        doc = self.get_object()
        confirm_delivery(doc, user=request.user)
        return Response({'status': 'delivery confirmed'})

    @action(detail=True, methods=['post'])
    def log_print(self, request, pk=None):
        doc = self.get_object()
        from .models import PrintRecord
        PrintRecord.objects.create(
            document=doc,
            printed_by=request.user,
            copies=request.data.get('copies', 1)
        )
        return Response({'status': 'print logged'})
    
    @action(detail=False, methods=['get'], url_path='by-qr/(?P<qr_code>[^/.]+)')
    def by_qr(self, request, qr_code=None):
        """Universal Scan Handler for structured data (DOC: or BAT:)"""
        if qr_code.startswith("DOC:"):
            number = qr_code.split(":", 1)[1]
            try:
                doc = Document.objects.get(number=number)
                serializer = self.get_serializer(doc)
                return Response(serializer.data)
            except Document.DoesNotExist:
                return Response({'error': 'Hujjat topilmadi'}, status=404)
        
        elif qr_code.startswith("BAT:"):
            batch_no = qr_code.split(":", 1)[1]
            from warehouse_v2.models import RawMaterialBatch
            from warehouse_v2.serializers import RawMaterialBatchSerializer
            try:
                batch = RawMaterialBatch.objects.get(batch_number=batch_no)
                return Response(RawMaterialBatchSerializer(batch).data)
            except RawMaterialBatch.DoesNotExist:
                return Response({'error': 'Partiya topilmadi'}, status=404)

        elif qr_code.startswith("BLK:"):
            block_no = qr_code.split(":", 1)[1]
            from production_v2.models import FinishedBlock
            from production_v2.serializers import FinishedBlockSerializer
            try:
                block = FinishedBlock.objects.get(block_id=block_no)
                return Response(FinishedBlockSerializer(block).data)
            except FinishedBlock.DoesNotExist:
                return Response({'error': 'Blok topilmadi'}, status=404)
        
        # Fallback to legacy UUID lookup if no prefix
        try:
            doc = Document.objects.get(qr_code=qr_code)
            serializer = self.get_serializer(doc)
            return Response(serializer.data)
        except:
            return Response({'error': 'QR kod tanilmadi'}, status=404)
