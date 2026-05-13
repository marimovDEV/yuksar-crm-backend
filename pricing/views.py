from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from .models import PricingRule
from .serializers import PricingRuleSerializer


class PricingRuleViewSet(viewsets.ModelViewSet):
    queryset = PricingRule.objects.all().order_by('-priority', '-created_at')
    serializer_class = PricingRuleSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = super().get_queryset()
        product = self.request.query_params.get('product')
        is_active = self.request.query_params.get('is_active')
        if product:
            qs = qs.filter(product__icontains=product)
        if is_active is not None:
            qs = qs.filter(is_active=is_active in ('true', '1', 'True'))
        return qs
