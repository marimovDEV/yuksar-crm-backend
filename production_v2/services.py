from decimal import Decimal
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from inventory.services import update_inventory, check_stock
from common_v2.services import log_action
from warehouse_v2.models import RawMaterialBatch, Warehouse, Material
from .models import Zames, BlockProduction, DryingProcess, ProductionOrder, ProductionOrderStage, StageActionLog, Bunker, ProductionPlan

def _ensure_production_order_document(order, user=None):
    from documents.models import Document, DocumentItem

    document, _ = Document.objects.get_or_create(
        type='PRODUCTION_ORDER',
        number=order.order_number,
        defaults={
            'status': 'CREATED',
            'created_by': user or order.responsible,
        },
    )

    if order.product and not document.items.exists():
        DocumentItem.objects.create(
            document=document,
            product=order.product,
            quantity=order.quantity,
            price_at_moment=0,
            batch_number=f"PROD-{order.order_number}",
        )
    return document

def _create_stage_update_document(stage, action, user=None, notes=''):
    from documents.models import Document, DocumentItem

    sequence_number = stage.sequence + 1
    document = Document.objects.create(
        type='STAGE_UPDATE',
        number=f"{stage.order.order_number}-{stage.stage_type}-{sequence_number:02d}-{action}",
        status='DONE' if action in ['FINISH', 'FAIL', 'RESET'] else 'CREATED',
        created_by=user or stage.current_operator or stage.order.responsible,
    )

    if stage.order.product:
        DocumentItem.objects.create(
            document=document,
            product=stage.order.product,
            quantity=stage.actual_quantity or stage.order.quantity,
            price_at_moment=0,
            batch_number=notes[:100] or None,
        )
    return document

def _mark_linked_invoice_ready(order, warehouse=None):
    if not order.source_order or not order.source_order.startswith('ORD-'):
        return

    try:
        from sales_v2.models import Invoice

        invoice = Invoice.objects.filter(
            invoice_number=order.source_order,
            status='IN_PRODUCTION'
        ).first()
        if not invoice:
            return

        invoice.status = 'READY'
        invoice.save(update_fields=['status'])

        production_batch = f"PROD-{order.order_number}"
        source_warehouse = warehouse
        for item in invoice.items.filter(product=order.product):
            if not item.batch_number:
                item.batch_number = production_batch
            if not item.source_warehouse_id and source_warehouse:
                item.source_warehouse = source_warehouse
            item.save(update_fields=['batch_number', 'source_warehouse'])
    except Exception:
        pass

def _generate_block_id():
    """Generates a unique block ID based on current year and sequence."""
    from .models import FinishedBlock
    year = timezone.now().year
    count = FinishedBlock.objects.count() + 1
    return f"BLK-{year}-{count:06d}"


def _append_block_timeline(block, status, notes='', user=None):
    from .models import BlockTimeline
    return BlockTimeline.objects.create(
        block=block,
        status=status,
        notes=notes,
        user=user
    )


def update_block_location(block, warehouse=None, zone=None, rack=None, user=None, notes=''):
    block.warehouse = warehouse
    if zone is not None:
        block.zone = zone
    if rack is not None:
        block.rack = rack
    block.save(update_fields=['warehouse', 'zone', 'rack', 'updated_at'])
    location_note = notes or f"Joylashuv yangilandi: {warehouse.name if warehouse else 'N/A'} / {block.zone or '-'} / {block.rack or '-'}"
    _append_block_timeline(block, 'LOCATION_UPDATED', location_note, user=user)
    return block


def transition_block_status(block, status, user=None, notes=''):
    block.transition_to(status, user=user)
    _append_block_timeline(block, status, notes or f"Holat yangilandi: {status}", user=user)
    return block

def complete_block_production(zames, form_number, block_count, length, width, height, density, user=None, shift='DAY'):
    """
    Enterprise: Records physical block production from Zames atomically.
    Creates individual FinishedBlock records for each block in the lot.
    """
    with transaction.atomic():
        # Auto-calculate volume: (L * W * H / 1e9) * count
        volume = (Decimal(str(length)) * Decimal(str(width)) * Decimal(str(height)) / Decimal('1e9')) * Decimal(str(block_count))
        
        block_lot = BlockProduction.objects.create(
            zames=zames,
            form_number=form_number,
            block_count=block_count,
            length=length,
            width=width,
            height=height,
            density=density,
            volume=volume,
            status='COOLING',
            operator=user or zames.operator,
            shift=shift
        )
        
        # Start Cooling/Drying Process
        DryingProcess.objects.create(block_production=block_lot)
        
        # Generate individual blocks for traceability
        from .models import FinishedBlock
        for _ in range(block_count):
            block_id = _generate_block_id()
            block = FinishedBlock.objects.create(
                block_id=block_id,
                lot=block_lot,
                status='COOLING',
                actual_density=density,
                length=length,
                width=width,
                height=height,
                qr_code_data=f"BLK:{block_id}",
            )
            _append_block_timeline(block, 'CREATED', f"Blok yaratildi. Forma: {form_number}, Zames: {zames.zames_number}", user=user)
            _append_block_timeline(block, 'COOLING_STARTED', "Sovitish bosqichi boshlandi", user=user)
        
        log_action(
            user=user,
            action='CREATE',
            module='Production',
            description=f"Bloklar quyildi: {block_count} dona ({density} kg/m3). Lot ID: {block_lot.id}",
            object_id=block_lot.id
        )
        return block_lot

def perform_block_qc(block_id, classification, status, notes='', actual_weight=None, actual_density=None, moisture=None, length=None, width=None, height=None, visual_defects='', user=None):
    """
    Enterprise: Performs QC on an individual block, updating its status and classification.
    """
    with transaction.atomic():
        from .models import FinishedBlock, BlockTimeline
        # Try finding by block_id (string) or id (integer)
        if isinstance(block_id, str) and block_id.startswith('BLK-'):
            block = FinishedBlock.objects.select_for_update().get(block_id=block_id)
        else:
            block = FinishedBlock.objects.select_for_update().get(id=block_id)
        
        block.classification = classification
        if actual_weight is not None: block.actual_weight = actual_weight
        if actual_density is not None: block.actual_density = actual_density
        if moisture is not None: block.moisture = moisture
        if length is not None: block.length = length
        if width is not None: block.width = width
        if height is not None: block.height = height
        if visual_defects: block.visual_defects = visual_defects
        
        block.transition_to(status, user=user)

        qc_status = 'QC_PASSED' if status == 'READY' else 'QC_FAILED' if status == 'RECYCLE' or classification == 'REJECT' else f"QC_{classification}"
        timeline_notes = f"{notes}\nDefects: {visual_defects}" if visual_defects else notes
        _append_block_timeline(block, qc_status, timeline_notes, user=user)
        if status == 'READY':
            _append_block_timeline(block, 'READY_FOR_TRANSFER', "Blok ombor/transfer uchun tayyor", user=user)
            # AUTO-WORKFLOW: QC PASSED → create CNCJob automatically
            _auto_create_cnc_job(block, user=user)
        elif status == 'RECYCLE':
            _append_block_timeline(block, 'DEFECT_RECORDED', timeline_notes or "Brak qayd etildi", user=user)

        return block


def _auto_create_cnc_job(block, user=None):
    """Auto-creates a CNCJob when a FinishedBlock passes QC (status=READY)."""
    try:
        from cnc_v2.models import CNCJob
        from warehouse_v2.models import Material
        # Don't create duplicate
        if CNCJob.objects.filter(input_finished_block=block).exists():
            return
        # Find a suitable output product (same material or a finished product)
        block_production = block.block_production
        output_product = None
        if block_production and block_production.zames:
            first_item = block_production.zames.items.first()
            if first_item:
                output_product = first_item.material
        if not output_product:
            output_product = Material.objects.filter(material_type='FINISHED').first()
        if not output_product:
            return  # Can't create without output product
        job_num = f"CNC-AUTO-{block.block_id or block.id}"
        block_production = getattr(block, 'lot', None)
        CNCJob.objects.create(
            job_number=job_num,
            input_finished_block=block,
            input_block=block_production,
            output_product=output_product,
            quantity_planned=block_production.block_count if block_production else 1,
            status='CREATED',
            priority=5,
        )
        log_action(
            user=user,
            action='CREATE',
            module='CNC',
            description=f"QC o'tganidan so'ng CNC ishi avtomatik yaratildi: {job_num}",
        )
    except Exception as e:
        # Log but don't fail the QC operation
        log_action(
            user=user,
            action='UPDATE',
            module='CNC',
            description=f"Auto CNCJob yaratishda xatolik: {str(e)}",
            status='ERROR',
        )

def finish_drying_process(block_production_id, user=None):
    """
    Enterprise: Finalizes drying phase, moves blocks to Sklad 2 atomically via InventoryService.
    """
    with transaction.atomic():
        # Lock block_batch to prevent race conditions
        block_batch = BlockProduction.objects.select_for_update().get(id=block_production_id)
        if block_batch.status != 'DRYING':
            raise ValidationError(f"Blok quritish holatida emas. Joriy status: {block_batch.status}")

        drying = block_batch.drying_processes.filter(end_time__isnull=True).first()
        if drying:
            drying.end_time = timezone.now()
            drying.save()

        block_batch.status = 'READY'
        
        # Sklad 2 is for semi-finished and ready blocks
        sklad2 = Warehouse.objects.filter(name__icontains='Sklad №2').first()
        block_batch.warehouse = sklad2
        block_batch.save()

        # Update Inventory Atomic Entry
        zames_material = block_batch.zames.items.first()
        product_ref = zames_material.material if zames_material else None
        
        if product_ref and sklad2:
            update_inventory(
                product=product_ref,
                warehouse=sklad2,
                qty=block_batch.block_count,
                batch_number=f"LOT-{block_batch.id}",
                user=user,
                reference=f"PROD-BLOCK-{block_batch.id}",
                notes=f"Forma: {block_batch.form_number}"
            )

        for block in block_batch.individual_blocks.all():
            block.warehouse = sklad2
            block.zone = 'COOLING-ZONE'
            block.rack = block_batch.form_number
            block.transition_to('QC_PENDING', user=user)
            _append_block_timeline(block, 'COOLING_FINISHED', "Sovitish yakunlandi", user=user)
            _append_block_timeline(block, 'MOVED_TO_SK2', f"{sklad2.name if sklad2 else 'SK-2'} ga o‘tkazildi", user=user)
            _append_block_timeline(block, 'QC_PENDING', "Sifat nazorati navbatiga qo‘yildi", user=user)

        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Bloklar quritildi va Sklad 2 ga o'tkazildi: {block_batch}",
            object_id=block_batch.id
        )
        return block_batch

def start_zames(zames, user=None):
    """
    Enterprise: Transitions Zames to IN_PROGRESS with strict stock validation.
    """
    with transaction.atomic():
        zames = Zames.objects.select_for_update().get(id=zames.id)
        
        # 1. Validate status transition (StateMachineMixin)
        zames.transition_to('IN_PROGRESS', user=user)
        
        # 2. Check stock availability in Sklad 1
        sklad1 = Warehouse.objects.filter(name__icontains='Sklad №1').first()
        if not sklad1:
             sklad1 = Warehouse.objects.first()

        for item in zames.items.all():
            if not check_stock(item.material, sklad1, item.quantity, batch_number=item.batch.batch_number if item.batch else None):
                raise ValidationError(f"Xom-ashyo yetarli emas: {item.material.name}. Omborda yetarli qoldiq yo'q.")

        zames.start_time = timezone.now()
        zames.save()
        
        return zames

def finish_zames(zames, output_weight, user=None):
    """
    Enterprise Hardening: Finalizes Zames, deducts inventory via Service Layer, 
    calculates costs, and adds expanded product to Sklad 2.
    """
    with transaction.atomic():
        zames = Zames.objects.select_for_update().get(id=zames.id)
        
        total_mix_cost = Decimal('0')
        accounting_lines = []

        sklad1 = Warehouse.objects.filter(name__icontains='Sklad №1').first() or Warehouse.objects.first()
        sklad2 = Warehouse.objects.filter(name__icontains='Sklad №2').first()

        # 1. Deduct Input Materials atomically
        for item in zames.items.all():
            price_per_unit = item.batch.price_per_unit if item.batch else item.material.price
            item.unit_cost = price_per_unit
            item.total_cost = Decimal(str(item.quantity)) * price_per_unit
            item.save()
            
            total_mix_cost += item.total_cost

            # Centralized stock deduction
            update_inventory(
                product=item.material,
                warehouse=sklad1,
                qty=-Decimal(str(item.quantity)),
                batch_number=item.batch.batch_number if item.batch else None,
                user=user or zames.operator,
                reference=f"ZAMES-CONSUMPTION-{zames.zames_number}"
            )

        # 2. Update Zames details with State Machine
        zames.output_weight = output_weight
        zames.input_weight = sum(item.quantity for item in zames.items.all())
        zames.end_time = timezone.now()
        zames.transition_to('DONE', user=user)
        
        # 3. Create Expanded Material Entry atomically
        expanded_material = Material.objects.filter(category='SEMI').first()
        if expanded_material and sklad2:
            update_inventory(
                product=expanded_material,
                warehouse=sklad2,
                qty=Decimal(str(output_weight)),
                batch_number=f"EXP-{zames.zames_number}",
                user=user or zames.operator,
                reference=f"ZAMES-OUTPUT-{zames.zames_number}"
            )

        # 4. Pipeline Integration (StateMachine + Transition)
        linked_stage = ProductionOrderStage.objects.filter(
            related_id=zames.id, 
            stage_type='ZAMES', 
            status='ACTIVE'
        ).first()
        
        if linked_stage:
            transition_to_next_stage(linked_stage.id, user=user)

        return zames

def transition_to_next_stage(stage_id, user=None, related_id=None):
    """
    Enterprise: Advances the production pipeline using StateMachineMixin.
    """
    with transaction.atomic():
        current_stage = ProductionOrderStage.objects.select_for_update().select_related('order').get(id=stage_id)
        if current_stage.status == 'DONE':
            return current_stage.order

        order = current_stage.order

        # Complete current stage with audit
        current_stage.transition_to('DONE', user=user)
        current_stage.completed_at = timezone.now()
        if related_id:
            current_stage.related_id = related_id
        current_stage.save()

        # Release Resources (Bunker)
        if current_stage.stage_type == 'BUNKER' and current_stage.related_id:
            try:
                from .models import BunkerLoad
                load = BunkerLoad.objects.filter(id=current_stage.related_id).first()
                if load:
                    bunker = Bunker.objects.select_for_update().get(id=load.bunker.id)
                    bunker.is_occupied = False
                    bunker.save()
            except Exception: pass

        # Activate Next Stage
        next_stage = order.stages.filter(sequence=current_stage.sequence + 1).first()
        if next_stage:
            next_stage.transition_to('PENDING', user=user)
        else:
            order.transition_to('COMPLETED', user=user)
            order.progress = Decimal('100.00')
            order.save()
            
            # Final Stock Update for Finished Goods
            sklad4 = Warehouse.objects.filter(name__icontains='4').first()
            if sklad4 and order.product:
                update_inventory(
                    product=order.product,
                    warehouse=sklad4,
                    qty=Decimal(str(order.quantity)),
                    batch_number=f"PROD-{order.order_number}",
                    reference=f"ORDER-FINISHED-{order.order_number}"
                )
            
            # Mark Linked Invoice Ready
            _mark_linked_invoice_ready(order, warehouse=sklad4)

        # Update Progress
        total_stages = order.stages.count()
        completed_count = order.stages.filter(status='DONE').count()
        if total_stages > 0:
            order.progress = (Decimal(str(completed_count)) / Decimal(str(total_stages))) * Decimal('100.00')
            order.save()

        return order

def start_production_stage(stage_id, user=None, extra_data=None):
    """
    Enterprise: Securely starts a stage with Resource Check and StateMachine.
    """
    with transaction.atomic():
        stage = ProductionOrderStage.objects.select_for_update().select_related('order').get(id=stage_id)
        
        if stage.status == 'ACTIVE':
            return stage
        
        # Resource: Bunker Locking
        if stage.stage_type == 'BUNKER':
            bunker_id = extra_data.get('bunker_id') if extra_data else None
            if not bunker_id: raise ValidationError("Bunker tanlanmagan.")
            
            bunker = Bunker.objects.select_for_update().get(id=bunker_id)
            if bunker.is_occupied:
                raise ValidationError(f"Bunker {bunker.name} band.")
            
            bunker.is_occupied = True
            bunker.last_occupied_at = timezone.now()
            bunker.save()

        stage.transition_to('ACTIVE', user=user)
        stage.started_at = stage.started_at or timezone.now()
        stage.current_operator = user
        _create_stage_update_document(stage, 'START', user=user)
        stage.save()
        return stage

def create_production_order(product, quantity, order_number=None, deadline=None, user=None, source="STOCK", priority='MEDIUM'):
    """
    Enterprise: Creates a new order and initializes pipeline atomically.
    """
    if not order_number:
        order_number = f"PN-{timezone.now().strftime('%y%m%d%H%M%S')}"

    with transaction.atomic():
        order = ProductionOrder.objects.create(
            order_number=order_number,
            product=product,
            quantity=quantity,
            deadline=deadline,
            responsible=user,
            source_order=source,
            priority=priority,
            status='PENDING'
        )

        _ensure_production_order_document(order, user=user)

        stages = [('ZAMES', 'Z'), ('DRYING', 'D'), ('BUNKER', 'B'), ('FORMOVKA', 'F'), ('BLOK', 'B'), ('CNC', 'C'), ('DEKOR', 'D')]
        for i, (code, _) in enumerate(stages):
            ProductionOrderStage.objects.create(order=order, stage_type=code, sequence=i, status='PENDING')
        
        order.transition_to('IN_PROGRESS', user=user)
        return order

def assign_task_to_operator(stage_id, operator_id, user=None):
    from django.contrib.auth import get_user_model
    User = get_user_model()
    
    with transaction.atomic():
        stage = ProductionOrderStage.objects.select_for_update().get(id=stage_id)
        operator = User.objects.get(id=operator_id)
        
        stage.current_operator = operator
        stage.save()
        
        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Topshiriq biriktirildi: {stage.get_stage_type_display()} -> {operator.username}",
            object_id=stage.id
        )
        return stage

def fail_production_stage(stage_id, reason, user=None):
    with transaction.atomic():
        stage = ProductionOrderStage.objects.select_for_update().get(id=stage_id)
        stage.transition_to('FAILED', user=user)
        
        StageActionLog.objects.create(
            order=stage.order,
            stage=stage,
            stage_type=stage.stage_type,
            action='FAIL',
            user=user,
            notes=reason
        )
        return stage

def force_release_bunker(bunker_id, user=None):
    with transaction.atomic():
        bunker = Bunker.objects.select_for_update().get(id=bunker_id)
        bunker.is_occupied = False
        bunker.save()
        
        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Bunker majburiy bo'shatildi: {bunker.name}",
            object_id=bunker.id
        )
        return bunker

def force_complete_stage(stage_id, user=None, reason=None):
    with transaction.atomic():
        stage = ProductionOrderStage.objects.select_for_update().get(id=stage_id)
        stage.transition_to('DONE', user=user, force=True)
        
        stage.completed_at = timezone.now()
        stage.save()
        
        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Bosqich majburiy yakunlandi: {stage.get_stage_type_display()} - {reason}",
            object_id=stage.id
        )
        
        order = stage.order
        total_stages = order.stages.count()
        completed_count = order.stages.filter(status='DONE').count()
        
        if total_stages > 0:
            order.progress = (Decimal(str(completed_count)) / Decimal(str(total_stages))) * Decimal('100.00')
            order.save()
            
        if completed_count == total_stages:
            order.transition_to('COMPLETED', user=user)
            order.save()
            
            # Final Stock Update for Finished Goods
            sklad4 = Warehouse.objects.filter(name__icontains='4').first()
            if sklad4 and order.product:
                update_inventory(
                    product=order.product,
                    warehouse=sklad4,
                    qty=Decimal(str(order.quantity)),
                    batch_number=f"PROD-{order.order_number}",
                    reference=f"ORDER-FINISHED-{order.order_number}"
                )
            
            # Mark Linked Invoice Ready
            _mark_linked_invoice_ready(order, warehouse=sklad4)
            
        return order

def reset_stage_to_pending(stage_id, user=None, reason=None):
    with transaction.atomic():
        stage = ProductionOrderStage.objects.select_for_update().get(id=stage_id)
        stage.transition_to('PENDING', user=user)
        
        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Bosqich qayta tiklandi: {stage.get_stage_type_display()} - {reason}",
            object_id=stage.id
        )
        return stage

def calculate_plan_material_needs(plan_id):
    plan = ProductionPlan.objects.get(id=plan_id)
    needs = {}
    
    for order in plan.orders.all():
        if order.product and hasattr(order.product, 'recipes'):
            recipe = order.product.recipes.filter(is_active=True).first()
            if recipe:
                for item in recipe.items.all():
                    mat_id = str(item.material.id)
                    qty = int(item.quantity * order.quantity)
                    needs[mat_id] = needs.get(mat_id, 0) + qty
    
    return needs

def start_plan(plan_id, user=None):
    with transaction.atomic():
        plan = ProductionPlan.objects.select_for_update().get(id=plan_id)
        plan.status = 'ACTIVE'
        plan.start_time = timezone.now()
        plan.save()
        
        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Plan boshlandi: {plan}",
            object_id=plan.id
        )
        return plan

def complete_plan(plan_id, actual_volume, user=None):
    with transaction.atomic():
        plan = ProductionPlan.objects.select_for_update().get(id=plan_id)
        plan.status = 'COMPLETED'
        plan.end_time = timezone.now()
        plan.actual_volume = actual_volume
        plan.save()
        
        log_action(
            user=user,
            action='UPDATE',
            module='Production',
            description=f"Plan yakunlandi: {plan} - Hajm: {actual_volume}",
            object_id=plan.id
        )
        return plan

def perform_quality_check(order_id, status, notes='', waste_weight=0, inspector=None):
    with transaction.atomic():
        order = ProductionOrder.objects.select_for_update().get(id=order_id)
        
        qc = QualityCheck.objects.create(
            order=order,
            status=status,
            notes=notes,
            waste_weight=waste_weight,
            inspector=inspector
        )
        
        if status == 'PASSED':
            # Optionally transition order if custom flow requires
            pass
        elif status == 'FAILED':
            order.transition_to('FAILED', user=inspector)
            
        return qc
