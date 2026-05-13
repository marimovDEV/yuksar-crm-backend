from rest_framework import serializers
from .models import (
    Zames, Bunker, BunkerLoad, BlockProduction,
    DryingProcess, Recipe, RecipeItem, ZamesItem,
    ProductionOrder, ProductionOrderStage, ProductionPlan, QualityCheck,
    ProductionBatch, FinishedBlock, BlockTimeline
)
from warehouse_v2.serializers import MaterialSerializer

class RecipeItemSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    
    class Meta:
        model = RecipeItem
        fields = '__all__'

class RecipeSerializer(serializers.ModelSerializer):
    items = RecipeItemSerializer(many=True, read_only=True)
    
    class Meta:
        model = Recipe
        fields = '__all__'

class ZamesItemSerializer(serializers.ModelSerializer):
    material_name = serializers.ReadOnlyField(source='material.name')
    
    class Meta:
        model = ZamesItem
        fields = '__all__'

class ZamesSerializer(serializers.ModelSerializer):
    items = ZamesItemSerializer(many=True, required=False)
    recipe_name = serializers.ReadOnlyField(source='recipe.name')
    operator_name = serializers.ReadOnlyField(source='operator.username')
    stage_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    
    class Meta:
        model = Zames
        fields = [
            'id', 'zames_number', 'recipe', 'recipe_name', 'status', 
            'start_time', 'end_time', 'input_weight', 'output_weight', 
            'operator', 'operator_name', 'machine_id', 'created_at', 'items',
            'stage_id', 'production_batch'
        ]
        read_only_fields = ('created_at',)

    def create(self, validated_data):
        items_data = validated_data.pop('items', [])
        stage_id = validated_data.pop('stage_id', None)
        
        # Link to production batch if stage_id is provided
        if stage_id:
            try:
                stage = ProductionOrderStage.objects.get(id=stage_id)
                order = stage.order
                from .models import ProductionBatch
                batch, _ = ProductionBatch.objects.get_or_create(
                    batch_number=order.order_number,
                    defaults={'status': 'OPEN'}
                )
                validated_data['production_batch'] = batch
            except ProductionOrderStage.DoesNotExist:
                pass

        zames = Zames.objects.create(**validated_data)
        
        # Link the stage to this zames
        if stage_id:
            try:
                stage = ProductionOrderStage.objects.get(id=stage_id)
                stage.related_id = zames.id
                stage.status = 'ACTIVE'
                if not stage.started_at:
                    from django.utils import timezone
                    stage.started_at = timezone.now()
                stage.save()
            except ProductionOrderStage.DoesNotExist:
                pass

        for item_data in items_data:
            ZamesItem.objects.create(zames=zames, **item_data)
            
        return zames

class BunkerSerializer(serializers.ModelSerializer):
    bunkerNumber = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    batchNumber = serializers.SerializerMethodField()
    loadedAt = serializers.SerializerMethodField()

    class Meta:
        model = Bunker
        fields = ['id', 'name', 'bunkerNumber', 'status', 'batchNumber', 'loadedAt']

    def get_bunkerNumber(self, obj):
        # Extract number from name: "Bunker 1" -> "1"
        import re
        match = re.search(r'\d+', obj.name)
        return match.group() if match else obj.name

    def get_status(self, obj):
        active_load = obj.loads.order_by('-load_time').first()
        if not active_load:
            return 'Empty'
        
        from django.utils import timezone
        # If required time for aging has passed, it's 'Ready'
        aging_end = active_load.load_time + timezone.timedelta(minutes=active_load.required_time)
        if timezone.now() > aging_end:
            return 'Ready'
        return 'Aging'

    def get_batchNumber(self, obj):
        active_load = obj.loads.order_by('-load_time').first()
        if active_load and active_load.zames:
            return f"EXP-{active_load.zames.zames_number}"
        return None

    def get_loadedAt(self, obj):
        active_load = obj.loads.order_by('-load_time').first()
        return active_load.load_time if active_load else None

class BunkerLoadSerializer(serializers.ModelSerializer):
    zames_number = serializers.ReadOnlyField(source='zames.zames_number')
    bunker_name = serializers.ReadOnlyField(source='bunker.name')

    class Meta:
        model = BunkerLoad
        fields = '__all__'

class BlockTimelineSerializer(serializers.ModelSerializer):
    user_name = serializers.ReadOnlyField(source='user.username')
    
    class Meta:
        model = BlockTimeline
        fields = '__all__'

class FinishedBlockSerializer(serializers.ModelSerializer):
    timeline = BlockTimelineSerializer(many=True, read_only=True)
    classification_display = serializers.CharField(source='get_classification_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    warehouse_name = serializers.ReadOnlyField(source='warehouse.name')
    
    # Metadata from lot
    recipe_name = serializers.ReadOnlyField(source='lot.zames.recipe.name')
    operator_name = serializers.ReadOnlyField(source='lot.operator.username')
    shift_display = serializers.ReadOnlyField(source='lot.get_shift_display')
    produced_date = serializers.ReadOnlyField(source='lot.date')
    
    class Meta:
        model = FinishedBlock
        fields = '__all__'

class BlockProductionSerializer(serializers.ModelSerializer):
    zames_number = serializers.ReadOnlyField(source='zames.zames_number')
    operator_name = serializers.ReadOnlyField(source='operator.username')
    shift_display = serializers.CharField(source='get_shift_display', read_only=True)

    class Meta:
        model = BlockProduction
        fields = '__all__'

class DryingProcessSerializer(serializers.ModelSerializer):
    block_details = serializers.ReadOnlyField(source='block_production.__str__')

    class Meta:
        model = DryingProcess
        fields = '__all__'

class QualityCheckSerializer(serializers.ModelSerializer):
    inspector_name = serializers.ReadOnlyField(source='inspector.username')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    order_number = serializers.ReadOnlyField(source='order.order_number')
    photo_url = serializers.SerializerMethodField()

    class Meta:
        model = QualityCheck
        fields = '__all__'

    def get_photo_url(self, obj):
        if obj.photo:
            return obj.photo.url
        return None

class ProductionOrderStageSerializer(serializers.ModelSerializer):
    stage_type_display = serializers.CharField(source='get_stage_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    current_operator_name = serializers.ReadOnlyField(source='current_operator.username')

    class Meta:
        model = ProductionOrderStage
        fields = '__all__'

class ProductionOrderSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_sku = serializers.ReadOnlyField(source='product.sku')
    stages = ProductionOrderStageSerializer(many=True, read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    responsible_name = serializers.ReadOnlyField(source='responsible.username')
    quality_checks = QualityCheckSerializer(many=True, read_only=True)
    
    # Timeline
    action_logs = serializers.SerializerMethodField()

    class Meta:
        model = ProductionOrder
        fields = '__all__'

    def get_action_logs(self, obj):
        from .models import StageActionLog
        logs = StageActionLog.objects.filter(order=obj).order_by('-timestamp')
        return [{
            'id': log.id,
            'action': log.action,
            'stage': log.stage_type,
            'user': log.user.username if log.user else 'System',
            'timestamp': log.timestamp,
            'notes': log.notes
        } for log in logs]

class ProductionPlanSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    shift_display = serializers.CharField(source='get_shift_display', read_only=True)
    orders_detail = ProductionOrderSerializer(source='orders', many=True, read_only=True)

    class Meta:
        model = ProductionPlan
        fields = '__all__'

class ProductionBatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductionBatch
        fields = "__all__"
