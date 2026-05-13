from rest_framework import serializers
from .models import Cashbox, ExpenseCategory, FinancialTransaction, ClientBalance, InternalTransfer

class CashboxSerializer(serializers.ModelSerializer):
    responsible_person_name = serializers.ReadOnlyField(source='responsible_person.username')
    type_display = serializers.CharField(source='get_type_display', read_only=True)
    
    class Meta:
        model = Cashbox
        fields = '__all__'

class ExpenseCategorySerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = ExpenseCategory
        fields = '__all__'
        
    def get_children(self, obj):
        if obj.children.exists():
            return ExpenseCategorySerializer(obj.children.all(), many=True).data
        return []

class FinancialTransactionSerializer(serializers.ModelSerializer):
    cashbox_name = serializers.ReadOnlyField(source='cashbox.name')
    category_name = serializers.ReadOnlyField(source='category.name')
    customer_name = serializers.ReadOnlyField(source='customer.name')
    performed_by_name = serializers.ReadOnlyField(source='performed_by.username')
    approved_by_name = serializers.ReadOnlyField(source='approved_by.username')
    department_display = serializers.CharField(source='get_department_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = FinancialTransaction
        fields = '__all__'

class InternalTransferSerializer(serializers.ModelSerializer):
    from_cashbox_name = serializers.ReadOnlyField(source='from_cashbox.name')
    to_cashbox_name = serializers.ReadOnlyField(source='to_cashbox.name')
    performed_by_name = serializers.ReadOnlyField(source='performed_by.username')
    status_display = serializers.CharField(source='get_status_display', read_only=True)

    class Meta:
        model = InternalTransfer
        fields = '__all__'

class ClientBalanceSerializer(serializers.ModelSerializer):
    customer_name = serializers.ReadOnlyField(source='customer.name')
    
    class Meta:
        model = ClientBalance
        fields = '__all__'
