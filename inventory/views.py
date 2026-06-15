from rest_framework import viewsets, permissions, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import InventoryBatch, InventoryMovement
from .serializers import InventoryBatchSerializer, InventoryMovementSerializer
from accounts.permissions import IsWarehouseOperator, IsProductionRelated, IsAdminOrDirectorOrAccountant

class InventoryBatchViewSet(viewsets.ModelViewSet):
    """
    Inventarizatsiya partiyalari — omborchilar va ishlab chiqarish xodimlari ko'radi.
    Yaratish/o'chirish faqat omborchi uchun.
    """
    queryset = InventoryBatch.objects.all().order_by('-created_at')
    serializer_class = InventoryBatchSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['product', 'location', 'status', 'source']
    search_fields = ['batch_number', 'product__name']
    ordering_fields = ['created_at', 'current_weight']

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            # Omborchi, ishlab chiqarish, direktor, buxgalter o'qiy oladi
            return [IsWarehouseOperator() | IsProductionRelated() | IsAdminOrDirectorOrAccountant()]
        return [IsWarehouseOperator()]

    def perform_destroy(self, instance):
        # Soft delete
        instance.is_deleted = True
        instance.save()

class InventoryMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Inventarizatsiya harakatlari — faqat o'qish.
    Omborchi, ishlab chiqarish va analitika uchun.
    """
    queryset = InventoryMovement.objects.all().order_by('-timestamp')
    serializer_class = InventoryMovementSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter]
    filterset_fields = ['batch', 'type', 'from_location', 'to_location']
    search_fields = ['reference', 'batch__batch_number']

    def get_permissions(self):
        return [IsWarehouseOperator() | IsProductionRelated() | IsAdminOrDirectorOrAccountant()]
