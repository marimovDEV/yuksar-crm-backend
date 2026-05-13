from rest_framework import serializers
from .models import PricingRule


class PricingRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = PricingRule
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')
