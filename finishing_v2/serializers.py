from rest_framework import serializers
from .models import FinishingJob, FinishingStageLog

class FinishingStageLogSerializer(serializers.ModelSerializer):
    operator_name = serializers.ReadOnlyField(source='operator.username')
    
    class Meta:
        model = FinishingStageLog
        fields = '__all__'

class FinishingJobSerializer(serializers.ModelSerializer):
    operator_name = serializers.ReadOnlyField(source='operator.username')
    product_name = serializers.ReadOnlyField(source='product.name')
    stage_display = serializers.CharField(source='get_current_stage_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    stage_logs = FinishingStageLogSerializer(many=True, read_only=True)
    input_finished_block_status = serializers.ReadOnlyField(source='input_finished_block.status')
    input_finished_block_code = serializers.ReadOnlyField(source='input_finished_block.block_id')
    
    # Calculate progress % (4 stages)
    progress = serializers.SerializerMethodField()

    class Meta:
        model = FinishingJob
        fields = '__all__'
        read_only_fields = ['job_number']

    def get_progress(self, obj):
        stages = [s[0] for s in FinishingJob.STAGE_CHOICES]
        try:
            idx = stages.index(obj.current_stage)
            return int(((idx + 1) / len(stages)) * 100)
        except:
            return 0
