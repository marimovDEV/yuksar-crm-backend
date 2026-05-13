from django.db import transaction
from django.db.models import Sum, Avg, Count

from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import (
    Zames, Bunker, BunkerLoad, BlockProduction,
    DryingProcess, Recipe, ProductionOrder, ProductionOrderStage, ProductionPlan, QualityCheck,
    ProductionBatch, FinishedBlock, BlockTimeline
)
from .serializers import (
    ZamesSerializer, BunkerSerializer, BunkerLoadSerializer,
    BlockProductionSerializer, DryingProcessSerializer,
    RecipeSerializer, ProductionOrderSerializer, ProductionPlanSerializer, QualityCheckSerializer,
    ProductionBatchSerializer, FinishedBlockSerializer, BlockTimelineSerializer
)
from accounts.permissions import IsAdmin, IsProductionOperator, IsProductionRelated, get_user_role_name
from .services import (
    start_zames, finish_zames, create_production_order,
    complete_block_production, finish_drying_process,
    transition_to_next_stage, assign_task_to_operator,
    calculate_plan_material_needs, start_plan, complete_plan,
    perform_quality_check, start_production_stage, fail_production_stage, force_release_bunker,
    force_complete_stage, reset_stage_to_pending, perform_block_qc
)

class RecipeViewSet(viewsets.ModelViewSet):
    queryset = Recipe.objects.all()
    serializer_class = RecipeSerializer
    permission_classes = [IsProductionRelated]

class ZamesViewSet(viewsets.ModelViewSet):
    queryset = Zames.objects.all()
    serializer_class = ZamesSerializer
    permission_classes = [IsProductionOperator]

    def get_queryset(self):
        user = self.request.user
        if get_user_role_name(user) in ['Bosh Admin', 'Admin', 'Ishlab chiqarish ustasi', 'SUPERADMIN', 'ADMIN']:
            return Zames.objects.all()
        # Operators only see zames assigned to them
        return Zames.objects.filter(operator=user)

    def perform_create(self, serializer):
        serializer.save(operator=self.request.user)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        zames = self.get_object()
        start_zames(zames, user=request.user)
        return Response({'status': 'Zames boshlandi', 'start_time': zames.start_time})

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        zames = self.get_object()
        output_weight = request.data.get('output_weight')
        if output_weight is None:
            return Response({'status': 'error', 'message': 'output_weight kiritilmadi'}, status=status.HTTP_400_BAD_REQUEST)
        
        finish_zames(zames, output_weight, user=request.user)
        return Response({'status': 'Zames yakunlandi', 'end_time': zames.end_time})

class BunkerViewSet(viewsets.ModelViewSet):
    queryset = Bunker.objects.all()
    serializer_class = BunkerSerializer
    permission_classes = [IsProductionOperator]

    @action(detail=True, methods=['post'], url_path='force-release')
    def force_release(self, request, pk=None):
        try:
            bunker = force_release_bunker(pk, user=request.user)
            return Response({'status': 'Bunker bo\'shatildi'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def formovka(self, request, pk=None):
        bunker = self.get_object()
        active_load = bunker.loads.order_by('-load_time').first()
        
        if not active_load:
            return Response({'error': 'Bunker bo\'sh yoki yuklanmagan'}, status=status.HTTP_400_BAD_REQUEST)
            
        zames = active_load.zames
        form_number = request.data.get('form_number', f"F-{zames.zames_number}")
        block_count = request.data.get('block_count', 12)
        # Physical parameters (mm)
        length = request.data.get('length', 1000)
        width = request.data.get('width', 1000)
        height = request.data.get('height', 1000)
        density = request.data.get('density', zames.recipe.density if zames and zames.recipe else 20)
        
        try:
            with transaction.atomic():
                block = complete_block_production(
                    zames=zames,
                    form_number=form_number,
                    block_count=block_count,
                    length=length,
                    width=width,
                    height=height,
                    density=density,
                    user=request.user,
                    shift=request.data.get('shift', 'DAY')
                )
                bunker.is_occupied = False
                bunker.save()
                return Response(BlockProductionSerializer(block).data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

class BunkerLoadViewSet(viewsets.ModelViewSet):
    queryset = BunkerLoad.objects.all()
    serializer_class = BunkerLoadSerializer
    permission_classes = [IsProductionOperator]

class BlockProductionViewSet(viewsets.ModelViewSet):
    queryset = BlockProduction.objects.all().order_by('-date', '-id')
    serializer_class = BlockProductionSerializer
    permission_classes = [IsProductionOperator]
    filterset_fields = ['status', 'warehouse']

    def perform_create(self, serializer):
        data = serializer.validated_data
        serializer.instance = complete_block_production(
            zames=data['zames'],
            form_number=data['form_number'],
            block_count=data['block_count'],
            length=data['length'],
            width=data['width'],
            height=data['height'],
            density=data['density'],
            user=self.request.user
        )

    @action(detail=True, methods=['post'])
    def transfer_to_cnc(self, request, pk=None):
        block_batch = self.get_object()
        if block_batch.status != 'READY':
            return Response({'error': 'Faqat TAYYOR bloklarni CNC ga berish mumkin.'}, status=400)
        
        block_batch.status = 'RESERVED'
        block_batch.save()
        return Response({'status': 'Blok CNC uchun rezerv qilindi', 'id': block_batch.id})

class DryingProcessViewSet(viewsets.ModelViewSet):
    queryset = DryingProcess.objects.all()
    serializer_class = DryingProcessSerializer
    permission_classes = [IsProductionOperator]
    filterset_fields = ['block_production']

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        drying = self.get_object()
        finish_drying_process(drying.block_production.id, user=request.user)
        return Response({'status': 'Quritish yakunlandi, bloklar Sklad 2 ga tushdi'})

class ProductionOrderViewSet(viewsets.ModelViewSet):
    queryset = ProductionOrder.objects.all().prefetch_related('stages').order_by('-created_at')
    serializer_class = ProductionOrderSerializer
    permission_classes = [IsProductionRelated]
    filterset_fields = ['status', 'priority']

    def _get_stage_for_order(self, order_pk, stage_id):
        try:
            stage = ProductionOrderStage.objects.get(id=stage_id, order_id=order_pk)
        except ProductionOrderStage.DoesNotExist:
            return None
        return stage

    def _is_supervisor(self, user):
        return user.is_superuser or get_user_role_name(user) in ['Bosh Admin', 'Admin', 'Ishlab chiqarish ustasi', 'SUPERADMIN', 'ADMIN']

    def create(self, request, *args, **kwargs):
        product_id = request.data.get('product')
        quantity = request.data.get('quantity')
        deadline = request.data.get('deadline')
        order_number = request.data.get('order_number')
        priority = request.data.get('priority', 'MEDIUM')
        
        from warehouse_v2.models import Material
        try:
            product = Material.objects.get(id=product_id)
        except Material.DoesNotExist:
            return Response({'error': 'Product not found'}, status=400)

        order = create_production_order(
            product=product,
            quantity=quantity,
            order_number=order_number,
            deadline=deadline,
            user=request.user,
            priority=priority
        )
        return Response(ProductionOrderSerializer(order).data, status=201)

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        stage_id = request.data.get('stage_id')
        related_id = request.data.get('related_id')
        actual_quantity = request.data.get('actual_quantity', 0)
        waste_amount = request.data.get('waste_amount', 0)
        
        if not stage_id:
            return Response({'error': 'stage_id is required'}, status=400)
            
        try:
            stage = self._get_stage_for_order(pk, stage_id)
            if not stage:
                return Response({'error': 'stage_id ushbu production orderga tegishli emas'}, status=400)

            # Update metrics before transition
            stage.actual_quantity = actual_quantity
            stage.waste_amount = waste_amount
            stage.save()
            
            order = transition_to_next_stage(stage_id, user=request.user, related_id=related_id)
            return Response(ProductionOrderSerializer(order).data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'], url_path='assign-task')
    def assign_task(self, request, pk=None):
        if not self._is_supervisor(request.user):
            return Response({'error': 'Bu amal faqat ustalar va adminlar uchun'}, status=403)
        stage_id = request.data.get('stage_id')
        operator_id = request.data.get('operator_id')
        
        if not stage_id or not operator_id:
            return Response({'error': 'stage_id and operator_id are required'}, status=400)
            
        stage = self._get_stage_for_order(pk, stage_id)
        if not stage:
            return Response({'error': 'stage_id ushbu production orderga tegishli emas'}, status=400)

        try:
            stage = assign_task_to_operator(stage_id, operator_id, user=request.user)
            return Response({'status': 'Topshiriq biriktirildi', 'operator': stage.current_operator.username})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'], url_path='start-stage')
    def start_stage(self, request, pk=None):
        stage_id = request.data.get('stage_id')
        extra_data = request.data.get('extra_data', {})
        if not stage_id:
            return Response({'error': 'stage_id is required'}, status=400)
        stage = self._get_stage_for_order(pk, stage_id)
        if not stage:
            return Response({'error': 'stage_id ushbu production orderga tegishli emas'}, status=400)

        try:
            start_production_stage(stage_id, user=request.user, extra_data=extra_data)
            return Response({'status': 'Bosqich boshlandi'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'], url_path='fail-stage')
    def fail_stage(self, request, pk=None):
        stage_id = request.data.get('stage_id')
        reason = request.data.get('reason', 'Noma\'lum xatolik')
        if not stage_id:
            return Response({'error': 'stage_id is required'}, status=400)
        stage = self._get_stage_for_order(pk, stage_id)
        if not stage:
            return Response({'error': 'stage_id ushbu production orderga tegishli emas'}, status=400)

        try:
            fail_production_stage(stage_id, reason, user=request.user)
            return Response({'status': 'Bosqich to\'xtatildi'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'], url_path='force-complete')
    def force_complete(self, request, pk=None):
        if not self._is_supervisor(request.user):
            return Response({'error': 'Bu amal faqat ustalar va adminlar uchun'}, status=403)
        stage_id = request.data.get('stage_id')
        reason = request.data.get('reason', 'Admin force complete')
        if not stage_id:
            return Response({'error': 'stage_id is required'}, status=400)
        stage = self._get_stage_for_order(pk, stage_id)
        if not stage:
            return Response({'error': 'stage_id ushbu production orderga tegishli emas'}, status=400)

        try:
            order = force_complete_stage(stage_id, user=request.user, reason=reason)
            return Response(ProductionOrderSerializer(order).data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=True, methods=['post'], url_path='reset-stage')
    def reset_stage(self, request, pk=None):
        if not self._is_supervisor(request.user):
            return Response({'error': 'Bu amal faqat ustalar va adminlar uchun'}, status=403)
        stage_id = request.data.get('stage_id')
        reason = request.data.get('reason', 'Admin reset')
        if not stage_id:
            return Response({'error': 'stage_id is required'}, status=400)
        stage = self._get_stage_for_order(pk, stage_id)
        if not stage:
            return Response({'error': 'stage_id ushbu production orderga tegishli emas'}, status=400)

        try:
            stage = reset_stage_to_pending(stage_id, user=request.user, reason=reason)
            # Fetch full order for consistent frontend update
            return Response(ProductionOrderSerializer(stage.order).data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

    @action(detail=False, methods=['get'])
    def kpi_summary(self, request):
        orders = ProductionOrder.objects.all()
        total_orders = orders.count()
        completed_orders = orders.filter(status='COMPLETED').count()
        
        stages = ProductionOrderStage.objects.all()
        # Sum only completed stages for "produced" metric to be accurate
        total_produced = stages.filter(status='DONE').aggregate(total=Sum('actual_quantity'))['total'] or 0
        total_waste = stages.aggregate(total=Sum('waste_amount'))['total'] or 0
        
        avg_waste_pct = (total_waste / total_produced * 100) if total_produced > 0 else 0
        
        return Response({
            'total_orders': total_orders,
            'completed_orders': completed_orders,
            'waste_metrics': {
                'total_produced': total_produced,
                'total_waste': total_waste,
                'avg_waste_pct': avg_waste_pct
            }
        })

class ProductionPlanViewSet(viewsets.ModelViewSet):
    queryset = ProductionPlan.objects.all().order_by('-date')
    serializer_class = ProductionPlanSerializer
    permission_classes = [IsProductionRelated]

    @action(detail=True, methods=['get'])
    def material_needs(self, request, pk=None):
        needs = calculate_plan_material_needs(pk)
        return Response(needs)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        plan = start_plan(pk, user=request.user)
        return Response(ProductionPlanSerializer(plan).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        actual_volume = request.data.get('actual_volume', 0)
        plan = complete_plan(pk, actual_volume, user=request.user)
        return Response(ProductionPlanSerializer(plan).data)

    @action(detail=True, methods=['post'], url_path='perform-qc')
    def perform_qc(self, request, pk=None):
        status = request.data.get('status') # PASSED or FAILED
        notes = request.data.get('notes', '')
        waste_weight = request.data.get('waste_weight', 0)
        
        if not status:
            return Response({'error': 'status is required'}, status=400)
            
        try:
            qc = perform_quality_check(
                order_id=pk,
                status=status,
                notes=notes,
                waste_weight=waste_weight,
                inspector=request.user
            )
            return Response(QualityCheckSerializer(qc).data)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class QualityCheckViewSet(viewsets.ModelViewSet):
    queryset = QualityCheck.objects.all().order_by('-created_at')
    serializer_class = QualityCheckSerializer
    permission_classes = [IsProductionRelated]
    filterset_fields = ['order', 'status', 'inspector']


class ProductionBatchViewSet(viewsets.ModelViewSet):
    queryset = ProductionBatch.objects.all().order_by('-start_time')
    serializer_class = ProductionBatchSerializer
    permission_classes = [IsProductionRelated]

class FinishedBlockViewSet(viewsets.ModelViewSet):
    queryset = FinishedBlock.objects.all().order_by('-created_at')
    serializer_class = FinishedBlockSerializer
    permission_classes = [IsProductionOperator]
    filterset_fields = ['lot', 'status', 'classification', 'block_id']

    @action(detail=True, methods=['post'], url_path='perform-qc')
    def perform_qc(self, request, pk=None):
        classification = request.data.get('classification')
        status_val = request.data.get('status')
        notes = request.data.get('notes', '')
        actual_weight = request.data.get('actual_weight')
        actual_density = request.data.get('actual_density')
        moisture = request.data.get('moisture')
        length = request.data.get('length')
        width = request.data.get('width')
        height = request.data.get('height')
        visual_defects = request.data.get('visual_defects', '')

        if not classification or not status_val:
            return Response({'error': 'classification and status are required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            block = perform_block_qc(
                block_id=pk,
                classification=classification,
                status=status_val,
                notes=notes,
                actual_weight=actual_weight,
                actual_density=actual_density,
                moisture=moisture,
                length=length,
                width=width,
                height=height,
                visual_defects=visual_defects,
                user=request.user
            )
            return Response(FinishedBlockSerializer(block).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'], url_path='by-id/(?P<block_id>[^/.]+)')
    def by_block_id(self, request, block_id=None):
        block = FinishedBlock.objects.filter(block_id=block_id).first()
        if not block:
            return Response({'error': 'Blok topilmadi'}, status=404)
        return Response(FinishedBlockSerializer(block).data)
