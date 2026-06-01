from rest_framework import serializers
from .models import Transaction
from products.serializers import ProductSerializer
from warehouse.serializers import WarehouseSerializer

class TransactionSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    from_warehouse_details = WarehouseSerializer(source='from_warehouse', read_only=True)
    to_warehouse_details = WarehouseSerializer(source='to_warehouse', read_only=True)
    block_id = serializers.ReadOnlyField(source='block.block_id')

    class Meta:
        model = Transaction
        fields = ('id', 'product', 'block', 'block_id', 'from_warehouse', 'to_warehouse', 'quantity', 'type', 'created_at', 
                  'product_details', 'from_warehouse_details', 'to_warehouse_details')
