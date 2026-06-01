from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from inventory.services import update_inventory
from transactions.services import create_transaction
from finance.services import record_double_entry
from common_v2.services import log_action
from warehouse_v2.models import Warehouse, Material
from .models import CNCJob, WasteProcessing
from production_v2.models import ProductionOrderStage

def start_cnc_job(job_id, operator=None):
    """
    Starts a CNC job, updating status and start time.
    """
    with transaction.atomic():
        job = CNCJob.objects.select_for_update().get(id=job_id)
        if job.status != 'Yaratildi' and job.status != 'CREATED':
            # Handle both localized and internal status if needed
             pass
        
        job.status = 'RUNNING'
        job.last_started_at = timezone.now()
        if not job.start_time:
            job.start_time = timezone.now()
        if operator:
            job.operator = operator
        job.save()

        # Update production stage if linked
        if job.order_stage:
            job.order_stage.status = 'ACTIVE'
            if not job.order_stage.started_at:
                job.order_stage.started_at = timezone.now()
            job.order_stage.save()

        if job.input_finished_block:
            from production_v2.services import transition_block_status
            transition_block_status(job.input_finished_block, 'CUTTING', user=operator or job.operator)

        log_action(
            user=operator or job.operator,
            action='UPDATE',
            module='CNC',
            description=f"CNC Ishi boshlandi: {job.job_number}",
            object_id=job.id
        )
        return job

def pause_cnc_job(job_id):
    with transaction.atomic():
        job = CNCJob.objects.select_for_update().get(id=job_id)
        if job.status == 'RUNNING' and job.last_started_at:
            elapsed = timezone.now() - job.last_started_at
            job.total_duration_seconds += int(elapsed.total_seconds())
        
        job.status = 'PAUSED'
        job.save()
        return job

def finish_cnc_job(job_id, finished_qty, waste_m3, operator=None):
    """
    Completes a CNC job, deducts input block stock, and adds output product to Sklad 3.
    """
    with transaction.atomic():
        job = CNCJob.objects.select_for_update().get(id=job_id)
        if job.status == 'COMPLETED':
            return job
        if finished_qty < 0:
            raise ValidationError("finished_qty manfiy bo'lishi mumkin emas.")
        if waste_m3 < 0:
            raise ValidationError("waste_m3 manfiy bo'lishi mumkin emas.")
        if finished_qty > job.quantity_planned:
            raise ValidationError("Tayyor mahsulot miqdori rejalashtirilgan miqdordan oshib ketdi.")

        # 1. Deduct from Input Block (Sklad 2)
        block = job.input_block
        # How many blocks did it consume? Usually 1 job = 1 or more blocks.
        # For simplicity, let's assume this job consumes the assigned block volume partially or fully.
        # If the user specifies quantity_finished, we should know how many blocks that represents.
        # TZ says transformation: 1 block -> many decorative products.
        
        # We deduct the entire block if it's a standard one-job-per-block workflow, 
        # or we calculate the volume.
        consumed_volume_m3 = (block.volume / block.block_count) if block.block_count > 0 else 0
        
        input_product = None
        if hasattr(block.zames, 'items'):
            first_item = block.zames.items.first()
            if first_item:
                input_product = first_item.material
        
        if input_product:
            create_transaction(
                product=input_product,
                from_wh=block.warehouse,
                to_wh=None, # Consumed
                qty=1, # 1 block unit
                trans_type='PRODUCTION',
                batch_number=f"LOT-{block.id}"
            )
        
        # Always update BlockProduction count
        if block.block_count <= 0:
            raise ValidationError("Kesish uchun mavjud blok qolmagan.")
        block.block_count -= 1
        if block.block_count <= 0:
            block.status = 'SOLD' # Or something like 'CONSUMED'
        block.save()

        # 2. Add Finished Products to Sklad 3
        sklad3 = Warehouse.objects.filter(name__icontains='Sklad №3').first()
        if not sklad3:
            # Fallback to creating or finding a suitable warehouse
            sklad3, _ = Warehouse.objects.get_or_create(name='Sklad №3 (Ichki)')

        create_transaction(
            product=job.output_product,
            from_wh=None,
            to_wh=sklad3,
            qty=finished_qty,
            trans_type='PRODUCTION',
            batch_number=job.job_number
        )
        
        # Finance: WIP (Decorative) -> WIP (Blocks)
        # Cost move (placeholder value for now)
        from decimal import Decimal
        record_double_entry(
            description=f"CNC Kesish yakunlandi: {job.job_number}",
            entries=[
                {'account_code': '2020', 'debit': Decimal('0'), 'credit': Decimal('0')}, # WIP Move
            ],
            reference=job.job_number,
            user=operator or job.operator
        )

        # 3. Record Results & Duration
        if job.status == 'RUNNING' and job.last_started_at:
            elapsed = timezone.now() - job.last_started_at
            job.total_duration_seconds += int(elapsed.total_seconds())

        job.waste_m3 = waste_m3
        job.quantity_finished = finished_qty
        job.status = 'COMPLETED'
        job.end_time = timezone.now()
        job.save()

        if job.input_finished_block:
            from production_v2.services import transition_block_status
            transition_block_status(job.input_finished_block, 'PACKAGED', user=operator or job.operator)

        # Assuming 1m3 of EPS is ~15-20kg. Let's use 15kg as constant if not specified.
        waste_kg = waste_m3 * 15 
        WasteProcessing.objects.create(
            job=job,
            waste_amount_kg=waste_kg,
            status='RAW',
            operator=operator or job.operator
        )

        # 4. Update Production Order Stage
        if job.order_stage:
            from production_v2.services import transition_to_next_stage
            transition_to_next_stage(job.order_stage.id, user=operator or job.operator, related_id=job.id)

        log_action(
            user=operator or job.operator,
            action='UPDATE',
            module='CNC',
            description=f"CNC Ishi yakunlandi: {job.job_number}. Tayyor: {finished_qty}, Chiqindi: {waste_m3}m3",
            object_id=job.id
        )
        return job
