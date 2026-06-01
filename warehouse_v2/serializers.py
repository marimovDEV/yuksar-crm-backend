from decimal import Decimal
from rest_framework import serializers
from django.db import transaction
from .models import (
    Supplier, Material, RawMaterialBatch, Warehouse, Stock, 
    WarehouseTransfer, PurchaseOrder, PurchaseOrderItem, InventoryAudit, InventoryAuditLine
)
from inventory.services import update_inventory

class SupplierSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    class Meta:
        model = Supplier
        fields = '__all__'

class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    material_unit = serializers.ReadOnlyField(source='material.unit')
    
    class Meta:
        model = PurchaseOrderItem
        fields = '__all__'

class PurchaseOrderSerializer(serializers.ModelSerializer):
    items = PurchaseOrderItemSerializer(many=True, read_only=True)
    supplier_name = serializers.ReadOnlyField(source='supplier.name')
    created_by_name = serializers.ReadOnlyField(source='created_by.full_name')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = PurchaseOrder
        fields = '__all__'

class MaterialSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source='get_category_display', read_only=True)
    
    class Meta:
        model = Material
        fields = ['id', 'name', 'sku', 'category', 'category_display', 'unit', 'price', 'description']

class RawMaterialBatchSerializer(serializers.ModelSerializer):
    supplier_name = serializers.ReadOnlyField(source='supplier.name')
    material_name = serializers.ReadOnlyField(source='material.name')
    responsible_user_name = serializers.ReadOnlyField(source='responsible_user.full_name')

    class Meta:
        model = RawMaterialBatch
        fields = '__all__'

    def create(self, validated_data):
        with transaction.atomic():
            instance = super().create(validated_data)
            # Enterprise Update: Centralized Stock Update via Service
            # Default warehouse for raw materials is Sklad 1
            warehouse, _ = Warehouse.objects.get_or_create(name='Sklad 1 (Xom Ashyo)')
            update_inventory(
                product=instance.material,
                warehouse=warehouse,
                qty=instance.quantity_kg,
                batch_number=instance.batch_number,
                user=instance.responsible_user,
                reference=f"RECEIPT-{instance.invoice_number}"
            )
            return instance

class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = '__all__'

class StockSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    material_price = serializers.ReadOnlyField(source='material.price')
    material_unit = serializers.ReadOnlyField(source='material.unit')
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    
    available_quantity = serializers.SerializerMethodField()
    reserved_quantity = serializers.SerializerMethodField()
    total_value = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = Stock
        fields = '__all__'

    def get_reserved_quantity(self, obj):
        from django.db.models import Sum
        return RawMaterialBatch.objects.filter(
            material=obj.material, 
            status__in=['IN_STOCK', 'RESERVED']
        ).aggregate(s=Sum('reserved_quantity'))['s'] or 0

    def get_available_quantity(self, obj):
        reserved = self.get_reserved_quantity(obj)
        return max(0, obj.quantity - reserved)

    def get_total_value(self, obj):
        return float(obj.quantity) * float(obj.material.price)

    def get_status(self, obj):
        if obj.quantity <= obj.min_level:
            return 'CRITICAL'
        if obj.quantity <= obj.min_level * Decimal('1.5'):
            return 'LOW'
        return 'OK'

class WarehouseTransferSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    material_sku = serializers.ReadOnlyField(source='material.sku')
    material_unit = serializers.ReadOnlyField(source='material.unit')
    from_warehouse_name = serializers.ReadOnlyField(source='from_warehouse.name')
    to_warehouse_name = serializers.ReadOnlyField(source='to_warehouse.name')
    batch_number = serializers.ReadOnlyField(source='batch.batch_number')
    block_id = serializers.ReadOnlyField(source='block.block_id')
    
    created_by_name = serializers.ReadOnlyField(source='created_by.full_name')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    transfer_type_display = serializers.CharField(source='get_transfer_type_display', read_only=True)

    class Meta:
        model = WarehouseTransfer
        fields = '__all__'
        extra_kwargs = {
            'material': {'required': False, 'allow_null': True},
            'batch': {'required': False, 'allow_null': True},
            'block': {'required': False, 'allow_null': True},
        }

    def validate(self, data):
        # Validation for Stock (Industrial Requirement)
        from_wh = data.get('from_warehouse')
        material = data.get('material')
        qty = data.get('quantity')
        block = data.get('block')

        if block and not material:
            zames = getattr(getattr(block, 'lot', None), 'zames', None)
            recipe = getattr(zames, 'recipe', None)
            if recipe and recipe.product:
                data['material'] = recipe.product
                material = recipe.product
        
        if from_wh and material and qty:
            stock = Stock.objects.filter(warehouse=from_wh, material=material).first()
            current_qty = stock.quantity if stock else 0
            if current_qty < qty:
                raise serializers.ValidationError({
                    "quantity": f"Omborda yetarli qoldiq yo'q. Mavjud: {current_qty} {material.unit}"
                })
        return data

    def create(self, validated_data):
        # In Industrial WMS, creation doesn't impact stock immediately.
        # It only creates a PENDING request.
        return super().create(validated_data)


class InventoryAuditLineSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    variance = serializers.ReadOnlyField()

    class Meta:
        model = InventoryAuditLine
        fields = '__all__'


class InventoryAuditSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    auditor_name = serializers.ReadOnlyField(source='auditor.full_name')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.full_name')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    lines = InventoryAuditLineSerializer(many=True, read_only=True)

    class Meta:
        model = InventoryAudit
        fields = '__all__'
