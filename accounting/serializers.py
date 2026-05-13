"""
Accounting Serializers — REST API serialization layer.
"""

from rest_framework import serializers
from .models import Account, JournalEntry, JournalEntryLine, FiscalPeriod, TaxRate


class AccountSerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True, default=None)
    parent_code = serializers.CharField(source='parent.code', read_only=True, default=None)
    account_type_display = serializers.CharField(source='get_account_type_display', read_only=True)
    children_count = serializers.SerializerMethodField()
    full_path = serializers.CharField(read_only=True)

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'account_type', 'account_type_display',
            'parent', 'parent_name', 'parent_code', 'children_count',
            'description', 'is_active', 'is_system', 'balance', 'full_path',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['balance', 'full_path', 'created_at', 'updated_at']

    def get_children_count(self, obj):
        return obj.children.count()


class AccountTreeSerializer(serializers.ModelSerializer):
    """Hierarchical tree view for Chart of Accounts."""
    children = serializers.SerializerMethodField()
    account_type_display = serializers.CharField(source='get_account_type_display', read_only=True)

    class Meta:
        model = Account
        fields = [
            'id', 'code', 'name', 'account_type', 'account_type_display',
            'balance', 'is_active', 'is_system', 'children',
        ]

    def get_children(self, obj):
        children = obj.children.filter(is_active=True).order_by('code')
        return AccountTreeSerializer(children, many=True).data


class JournalEntryLineSerializer(serializers.ModelSerializer):
    account_code = serializers.CharField(source='account.code', read_only=True)
    account_name = serializers.CharField(source='account.name', read_only=True)

    class Meta:
        model = JournalEntryLine
        fields = [
            'id', 'account', 'account_code', 'account_name',
            'debit', 'credit', 'description',
        ]


class JournalEntryLineCreateSerializer(serializers.Serializer):
    """For creating lines within a journal entry."""
    account_code = serializers.CharField(required=False)
    account_id = serializers.IntegerField(required=False)
    debit = serializers.DecimalField(max_digits=18, decimal_places=2, default=0)
    credit = serializers.DecimalField(max_digits=18, decimal_places=2, default=0)
    description = serializers.CharField(required=False, default='', allow_blank=True)


class JournalEntrySerializer(serializers.ModelSerializer):
    lines = JournalEntryLineSerializer(many=True, read_only=True)
    created_by_name = serializers.CharField(
        source='created_by.full_name', read_only=True, default=None
    )
    voided_by_name = serializers.CharField(
        source='voided_by.full_name', read_only=True, default=None
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    source_type_display = serializers.CharField(source='get_source_type_display', read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    total_debit = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    total_credit = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = JournalEntry
        fields = [
            'id', 'entry_number', 'date', 'description',
            'source_type', 'source_type_display', 'source_id', 'source_description',
            'status', 'status_display', 'reference', 'tax_rate',
            'total_amount', 'total_debit', 'total_credit', 'is_balanced',
            'fiscal_period',
            'created_by', 'created_by_name',
            'posted_at', 'voided_at', 'voided_by', 'voided_by_name', 'void_reason',
            'created_at', 'updated_at',
            'attachment',
            'lines',
        ]
        read_only_fields = [
            'entry_number', 'posted_at', 'voided_at', 'voided_by',
            'created_at', 'updated_at',
        ]


class JournalEntryCreateSerializer(serializers.Serializer):
    """Custom serializer for creating journal entries with lines."""
    date = serializers.DateField(required=False)
    description = serializers.CharField()
    source_type = serializers.ChoiceField(
        choices=JournalEntry.SourceType.choices,
        default='MANUAL'
    )
    source_id = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    source_description = serializers.CharField(required=False, default='', allow_blank=True)
    reference = serializers.CharField(required=False, default='', allow_blank=True)
    tax_rate_id = serializers.IntegerField(required=False, allow_null=True)
    auto_post = serializers.BooleanField(default=False)
    attachment = serializers.FileField(required=False, allow_null=True)
    lines = JournalEntryLineCreateSerializer(many=True, min_length=2)


class FiscalPeriodSerializer(serializers.ModelSerializer):
    closed_by_name = serializers.CharField(
        source='closed_by.full_name', read_only=True, default=None
    )

    class Meta:
        model = FiscalPeriod
        fields = [
            'id', 'name', 'start_date', 'end_date',
            'is_closed', 'closed_by', 'closed_by_name', 'closed_at',
            'created_at',
        ]
        read_only_fields = ['is_closed', 'closed_by', 'closed_at', 'created_at']


class TaxRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxRate
        fields = [
            'id', 'name', 'code', 'rate', 'is_active', 'description',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']
