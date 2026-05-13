from rest_framework import serializers
from .models import Dealer, DealerPayment, DealerOrder


class DealerPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealerPayment
        fields = '__all__'
        read_only_fields = ('created_by', 'date')


class DealerOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = DealerOrder
        fields = '__all__'
        read_only_fields = ('created_by', 'created_at', 'status')


class DealerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dealer
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at', 'debt')


class DealerListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dealer
        fields = [
            'id', 'name', 'phone', 'region', 'category', 'status',
            'credit_limit', 'debt', 'monthly_target', 'monthly_actual',
            'last_order', 'stir', 'address',
        ]
