from django.db import transaction
from django.utils import timezone
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from .models import FinishingJob, FinishingStageLog
from warehouse_v2.models import Warehouse, Material
from inventory.services import update_inventory
from finance.services import record_double_entry

def start_finishing_job(job_id, operator):
    job = get_object_or_404(FinishingJob, id=job_id)
    if job.status != 'PENDING':
        raise ValidationError("Ishni faqat 'Kutilmoqda' holatidan boshlash mumkin.")
    
    with transaction.atomic():
        job.status = 'RUNNING'
        job.operator = operator
        job.last_started_at = timezone.now()
        if not job.started_at:
            job.started_at = timezone.now()
        job.save()
        
        # Log first stage
        FinishingStageLog.objects.create(
            job=job,
            stage=job.current_stage,
            operator=operator
        )

        if job.input_finished_block:
            from production_v2.services import transition_block_status
            transition_block_status(job.input_finished_block, 'FINISHING', user=operator)
    return job

def advance_finishing_stage(job_id, operator):
    job = get_object_or_404(FinishingJob, id=job_id)
    if job.status == 'COMPLETED':
        raise ValidationError("Ish allaqachon tugallangan.")
    
    stages = [s[0] for s in FinishingJob.STAGE_CHOICES]
    current_index = stages.index(job.current_stage)
    
    if current_index >= len(stages) - 1:
        # If already at READY, calling advance completes the job
        return finish_finishing_job(job_id, finished_qty=job.quantity, waste_qty=0, operator=operator)

    next_stage = stages[current_index + 1]
    
    with transaction.atomic():
        # End current stage log
        last_log = job.stage_logs.filter(stage=job.current_stage, ended_at__isnull=True).last()
        if last_log:
            last_log.ended_at = timezone.now()
            last_log.save()
            
        # Update job
        job.current_stage = next_stage
        job.operator = operator
        # Ensure it's running if it was paused
        job.status = 'RUNNING' 
        job.last_started_at = timezone.now()
        job.save()
        
        # Start next stage log
        FinishingStageLog.objects.create(
            job=job,
            stage=next_stage,
            operator=operator
        )
    return job

def pause_finishing_job(job_id):
    job = get_object_or_404(FinishingJob, id=job_id)
    if job.status != 'RUNNING':
        raise ValidationError("Faqat jarayondagi ishni to'xtatish mumkin.")
        
    with transaction.atomic():
        job = FinishingJob.objects.select_for_update().get(id=job_id)
        if job.status == 'RUNNING' and job.last_started_at:
            elapsed = timezone.now() - job.last_started_at
            job.total_duration_seconds += int(elapsed.total_seconds())
        
        job.status = 'PAUSED'
        job.save()
        return job

def resume_finishing_job(job_id, operator):
    job = get_object_or_404(FinishingJob, id=job_id)
    if job.status != 'PAUSED':
        raise ValidationError("Faqat to'xtatilgan ishni davom ettirish mumkin.")
    
    job.status = 'RUNNING'
    job.operator = operator
    job.last_started_at = timezone.now()
    job.save()
    return job

def finish_finishing_job(job_id, finished_qty, waste_qty, operator):
    job = get_object_or_404(FinishingJob, id=job_id)
    if job.status == 'COMPLETED':
        return job
    if finished_qty < 0 or waste_qty < 0:
        raise ValidationError("finished_qty va waste_qty manfiy bo'lishi mumkin emas.")
    if finished_qty + waste_qty > job.quantity:
        raise ValidationError("Yakuniy va chiqindi miqdori rejalashtirilgan miqdordan oshib ketdi.")
        
    with transaction.atomic():
        # 1. Update Duration
        if job.status == 'RUNNING' and job.last_started_at:
            elapsed = timezone.now() - job.last_started_at
            job.total_duration_seconds += int(elapsed.total_seconds())

        # 2. Close logs
        last_log = job.stage_logs.filter(ended_at__isnull=True).last()
        if last_log:
            last_log.ended_at = timezone.now()
            last_log.save()
            
        # 3. Update job status and results
        job.status = 'COMPLETED'
        job.completed_at = timezone.now()
        job.finished_quantity = finished_qty
        job.waste_quantity = waste_qty
        job.save()

        if job.input_finished_block:
            from production_v2.services import transition_block_status
            transition_block_status(job.input_finished_block, 'PACKAGED', user=operator)
        
        # 4. Inventory Movement (Sklad 3 -> Sklad 4)
        # Assuming Sklad 3 (Production Output) -> Sklad 4 (Prepared for Sale)
        # Note: In real setup, you might want to deduct from Sklad 3 and add to Sklad 4
        # We use a custom inventory update service or transaction here if needed.
        # For now, let's keep the user's logic but use the actual quantities.
        
        sklad3 = Warehouse.objects.filter(name__icontains='Sklad №3').first()
        sklad4 = Warehouse.objects.filter(name__icontains='Sklad №4').first()
        if not sklad3:
            sklad3, _ = Warehouse.objects.get_or_create(name='Sklad №3')
        if not sklad4:
            sklad4, _ = Warehouse.objects.get_or_create(name='Sklad №4')

        # Ensure product category
        if job.product.category != 'FINISHED':
            job.product.category = 'FINISHED'
            job.product.save()

        # Update Sklad 3 (Deduct from CNC output) or Sklad 2 (Deduct raw block directly)
        if job.cnc_job:
            source_batch = job.cnc_job.job_number
            update_inventory(job.product, sklad3, -(finished_qty + waste_qty), batch_number=source_batch)
        elif job.input_finished_block:
            block = job.input_finished_block.lot
            input_product = None
            if hasattr(block.zames, 'items'):
                first_item = block.zames.items.first()
                if first_item:
                    input_product = first_item.material
            if input_product:
                from transactions.services import create_transaction
                create_transaction(
                    product=input_product,
                    from_wh=block.warehouse or sklad2,
                    to_wh=None, # Consumed
                    qty=1, # 1 block unit
                    trans_type='PRODUCTION',
                    batch_number=f"LOT-{block.id}"
                )
                if block.block_count > 0:
                    block.block_count -= 1
                    if block.block_count <= 0:
                        block.status = 'SOLD'
                    block.save()
        
        # Add finished to Sklad 4
        update_inventory(job.product, sklad4, finished_qty, batch_number=job.job_number)
        
        # Finance: Finished Goods (2030) -> WIP (2020)
        # Cost move (placeholder value for now)
        from decimal import Decimal
        record_double_entry(
            description=f"Pardozlash (Finishing) yakunlandi: {job.job_number}",
            entries=[
                {'account_code': '2030', 'debit': Decimal('0'), 'credit': Decimal('0')}, # Finished Goods
                {'account_code': '2020', 'debit': Decimal('0'), 'credit': Decimal('0')}, # WIP Move
            ],
            reference=job.job_number,
            user=operator
        )
        
        # ── Fix 7: Advance Production Pipeline Stage ──
        if job.order_stage:
            from production_v2.services import transition_to_next_stage
            transition_to_next_stage(job.order_stage.id, user=operator, related_id=job.id)
        
    return job
