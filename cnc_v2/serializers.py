from rest_framework import serializers
from .models import CNCJob, WasteProcessing

class CNCJobSerializer(serializers.ModelSerializer):
    operator_name = serializers.ReadOnlyField(source='operator.username')
    output_product_name = serializers.ReadOnlyField(source='output_product.name')
    input_block_number = serializers.ReadOnlyField(source='input_block.form_number')
    input_block_status = serializers.ReadOnlyField(source='input_block.status')
    input_finished_block_status = serializers.ReadOnlyField(source='input_finished_block.status')
    input_finished_block_code = serializers.ReadOnlyField(source='input_finished_block.block_id')
    
    class Meta:
        model = CNCJob
        fields = '__all__'

class WasteProcessingSerializer(serializers.ModelSerializer):
    operator_name = serializers.ReadOnlyField(source='operator.username')
    job_number = serializers.ReadOnlyField(source='job.job_number')
    source_department_display = serializers.CharField(source='get_source_department_display', read_only=True)
    reason_display = serializers.CharField(source='get_reason_display', read_only=True)

    class Meta:
        model = WasteProcessing
        fields = '__all__'
