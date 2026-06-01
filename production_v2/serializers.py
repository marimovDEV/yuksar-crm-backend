from rest_framework import serializers
from .models import (
    Zames, Bunker, BunkerLoad, BlockProduction,
    DryingProcess, Recipe, RecipeItem, ZamesItem,
    ProductionOrder, ProductionOrderStage, ProductionPlan, QualityCheck,
    ProductionBatch, FinishedBlock, BlockTimeline
)
from warehouse_v2.serializers import MaterialSerializer
from sales_v2.models import SaleItem, Invoice

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
    recipe_id = serializers.ReadOnlyField(source='lot.zames.recipe.id')
    zames_number = serializers.ReadOnlyField(source='lot.zames.zames_number')
    production_batch_number = serializers.ReadOnlyField(source='lot.zames.production_batch.batch_number')
    machine_id = serializers.ReadOnlyField(source='lot.zames.machine_id')
    operator_name = serializers.ReadOnlyField(source='lot.operator.username')
    shift_display = serializers.ReadOnlyField(source='lot.get_shift_display')
    produced_date = serializers.ReadOnlyField(source='lot.date')
    form_number = serializers.ReadOnlyField(source='lot.form_number')
    lot_density = serializers.ReadOnlyField(source='lot.density')
    lot_volume = serializers.ReadOnlyField(source='lot.volume')
    product_id = serializers.ReadOnlyField(source='lot.zames.recipe.product.id')
    product_name = serializers.ReadOnlyField(source='lot.zames.recipe.product.name')
    bunker_name = serializers.SerializerMethodField()
    cooling_time_hours = serializers.SerializerMethodField()
    current_location = serializers.SerializerMethodField()
    transfer_history = serializers.SerializerMethodField()
    defect_list = serializers.SerializerMethodField()
    commercial_info = serializers.SerializerMethodField()
    financial_analysis = serializers.SerializerMethodField()
    quality_metrics = serializers.SerializerMethodField()
    
    class Meta:
        model = FinishedBlock
        fields = '__all__'

    # ── Helper: find linked SaleItem for this block ──
    def _find_sale_item(self, obj):
        """Find SaleItem linked to this block's production batch."""
        try:
            zames = obj.lot.zames
            if not zames:
                return None
            pb = zames.production_batch
            if pb:
                # Direct FK match on production_batch
                item = SaleItem.objects.filter(
                    production_batch=pb
                ).select_related('invoice', 'invoice__customer').first()
                if item:
                    return item
                # Fallback: match by batch_number string
                item = SaleItem.objects.filter(
                    batch_number=pb.batch_number
                ).select_related('invoice', 'invoice__customer').first()
                if item:
                    return item
        except Exception:
            pass
        return None

    # ── Helper: compute block volume in m³ ──
    def _get_block_volume(self, obj):
        """Return single-block volume in m³."""
        length = obj.length or (obj.lot.length if obj.lot else 1000)
        width = obj.width or (obj.lot.width if obj.lot else 500)
        height = obj.height or (obj.lot.height if obj.lot else 500)
        return (length * width * height) / 1e9

    # ── Helper: check if block went through FINISHING ──
    def _went_through_finishing(self, obj):
        return obj.timeline.filter(status='FINISHING').exists()

    # ──────────────────────────────────────────────────
    # A) Financial Analysis
    # ──────────────────────────────────────────────────
    def get_financial_analysis(self, obj):
        try:
            volume = self._get_block_volume(obj)
            density = obj.actual_density or (obj.lot.density if obj.lot else None) or 20

            eps_cost = round(volume * density * 1.05 * 15000, 2)
            gas_cost = round(volume * 18000, 2)
            electricity_cost = round(volume * 9000, 2)
            labor_cost = round(volume * 27000, 2)
            finishing_cost = round(volume * 44000, 2) if self._went_through_finishing(obj) else 0
            total_cost = round(eps_cost + gas_cost + electricity_cost + labor_cost + finishing_cost, 2)

            # Determine sell price
            sell_price = None
            sale_item = self._find_sale_item(obj)
            if sale_item:
                total_blocks = FinishedBlock.objects.filter(lot__zames__production_batch=sale_item.production_batch).count() if sale_item.production_batch else 0
                if total_blocks and total_blocks > 0:
                    sell_price = round(float(sale_item.price) * float(sale_item.quantity) / total_blocks, 2)
                else:
                    sell_price = round(float(sale_item.price), 2)
            if sell_price is None:
                sell_price = round(volume * density * 28000, 2)

            margin = round(sell_price - total_cost, 2)
            margin_percent = round((margin / sell_price * 100), 2) if sell_price else 0

            return {
                'eps_cost': eps_cost,
                'gas_cost': gas_cost,
                'electricity_cost': electricity_cost,
                'labor_cost': labor_cost,
                'finishing_cost': finishing_cost,
                'total_cost': total_cost,
                'sell_price': sell_price,
                'margin': margin,
                'margin_percent': margin_percent,
            }
        except Exception:
            return None

    # ──────────────────────────────────────────────────
    # B) Quality Metrics
    # ──────────────────────────────────────────────────
    def get_quality_metrics(self, obj):
        try:
            density = obj.actual_density or (obj.lot.density if obj.lot else None) or 0
            moisture = obj.moisture or 0

            length = obj.length or (obj.lot.length if obj.lot else None)
            width = obj.width or (obj.lot.width if obj.lot else None)
            height = obj.height or (obj.lot.height if obj.lot else None)

            # Defect analysis
            defects = [d.strip() for d in (obj.visual_defects or '').split(',') if d.strip()]
            defect_count = len(defects)
            # Max possible defect types considered: 10
            defect_percent = round(min(defect_count / 10 * 100, 100), 2)

            # Operator score based on timeline quality
            timeline_entries = obj.timeline.all()
            has_recycle = timeline_entries.filter(status='RECYCLE').exists()
            base_score = 95 if not has_recycle else 70
            # Reduce proportionally for defects (each defect -3 points, min 40)
            operator_score = max(base_score - (defect_count * 3), 40)

            return {
                'density': density,
                'moisture': moisture,
                'dimensions': {
                    'length': length,
                    'width': width,
                    'height': height,
                },
                'defect_percent': defect_percent,
                'classification': obj.classification,
                'operator_score': operator_score,
            }
        except Exception:
            return None

    # ──────────────────────────────────────────────────
    # Existing methods
    # ──────────────────────────────────────────────────
    def get_bunker_name(self, obj):
        load = getattr(getattr(obj, 'lot', None), 'zames', None)
        if not load:
            return None
        bunker_load = obj.lot.zames.bunkerload_set.order_by('-load_time').select_related('bunker').first()
        return bunker_load.bunker.name if bunker_load and bunker_load.bunker else None

    def get_cooling_time_hours(self, obj):
        drying = obj.lot.drying_processes.order_by('-start_time').first() if obj.lot_id else None
        if not drying:
            return None
        end_time = drying.end_time or obj.updated_at
        return round((end_time - drying.start_time).total_seconds() / 3600, 2)

    def get_current_location(self, obj):
        return {
            'warehouse_id': obj.warehouse_id,
            'warehouse_name': obj.warehouse.name if obj.warehouse else None,
            'zone': obj.zone,
            'rack': obj.rack,
            'location_code': " / ".join([part for part in [obj.warehouse.name if obj.warehouse else None, obj.zone or None, obj.rack or None] if part]) or None,
        }

    def get_transfer_history(self, obj):
        transfers = obj.transfers.select_related('from_warehouse', 'to_warehouse', 'created_by').order_by('-created_at')
        return [{
            'id': transfer.id,
            'transfer_number': transfer.transfer_number,
            'status': transfer.status,
            'from_warehouse_name': transfer.from_warehouse.name if transfer.from_warehouse else None,
            'to_warehouse_name': transfer.to_warehouse.name if transfer.to_warehouse else None,
            'reason': transfer.reason,
            'notes': transfer.notes,
            'created_at': transfer.created_at,
            'approved_at': transfer.approved_at,
            'shipped_at': transfer.shipped_at,
            'received_at': transfer.received_at,
            'created_by_name': transfer.created_by.username if transfer.created_by else None,
        } for transfer in transfers]

    def get_defect_list(self, obj):
        if not obj.visual_defects:
            return []
        return [item.strip() for item in obj.visual_defects.split(',') if item.strip()]

    # ──────────────────────────────────────────────────
    # C) Commercial Info (upgraded with SaleItem lookup)
    # ──────────────────────────────────────────────────
    def get_commercial_info(self, obj):
        sale_item = self._find_sale_item(obj)
        if sale_item:
            inv = sale_item.invoice
            return {
                'reserved': obj.status == 'RESERVED',
                'sold': obj.status in ['SOLD', 'SHIPPED'],
                'customer': inv.customer.name if inv and inv.customer else None,
                'invoice_number': inv.invoice_number if inv else None,
                'invoice_date': inv.date if inv else None,
                'sell_price': float(sale_item.price),
                'payment_status': inv.status if inv else None,
                'invoice': inv.invoice_number if inv else None,
            }
        return {
            'reserved': obj.status == 'RESERVED',
            'sold': obj.status in ['SOLD', 'SHIPPED'],
            'invoice': None,
            'customer': None,
            'invoice_number': None,
            'invoice_date': None,
            'sell_price': None,
            'payment_status': None,
        }

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
