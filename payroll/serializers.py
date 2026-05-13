from rest_framework import serializers
from .models import PayrollRecord


class PayrollSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    employee_name = serializers.SerializerMethodField()

    class Meta:
        model = PayrollRecord
        fields = [
            'id', 'employee', 'name', 'employee_name', 'month',
            'base_salary', 'bonus', 'deduction', 'total',
            'status', 'paid_at', 'position', 'notes',
        ]
        read_only_fields = ('total', 'paid_at', 'paid_by')

    def get_name(self, obj):
        return obj.employee.full_name or obj.employee.username

    def get_employee_name(self, obj):
        return obj.employee.full_name or obj.employee.username
