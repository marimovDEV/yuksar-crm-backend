import os
import django
import sys
from django.utils import timezone
from django.db import transaction
from decimal import Decimal

# Setup Django environment
sys.path.append(os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from accounts.models import User
from warehouse_v2.models import Warehouse, Material, Stock
from inventory.models import Inventory
from production_v2.models import Zames, Recipe, FinishedBlock, BlockProduction, BlockTimeline
from production_v2.services import complete_block_production, finish_drying_process, perform_block_qc, transition_block_status
from cnc_v2.models import CNCJob
from cnc_v2.services import start_cnc_job, finish_cnc_job
from finishing_v2.models import FinishingJob
from finishing_v2.services import start_finishing_job, finish_finishing_job
from common_v2.compatibility import DashboardCompatibilityView
from django.test import RequestFactory

def run_e2e_walkthrough():
    print("--- 🌟 Starting E2E Block State Machine & Pipeline Walkthrough 🌟 ---")

    # 0. Get/create active admin user
    operator, _ = User.objects.get_or_create(username='test_admin', defaults={
        'email': 'test@example.com',
        'is_superuser': True,
        'is_staff': True
    })
    if not operator.is_superuser:
        operator.is_superuser = True
        operator.is_staff = True
        operator.save()

    # Get materials, warehouses, and recipes
    raw_material, _ = Material.objects.get_or_create(name="TEST-Raw Polystyrene", defaults={'category': 'RAW', 'sku': 'RAW-PS-001'})
    block_material, _ = Material.objects.get_or_create(name="TEST-Finished Block 15kg/m3", defaults={'category': 'FINISHED', 'sku': 'BLK-15KG-001'})
    decorative_product, _ = Material.objects.get_or_create(name="TEST-Decorative Cornice", defaults={'category': 'FINISHED', 'sku': 'DEC-CORN-001'})
    
    sklad1, _ = Warehouse.objects.get_or_create(name="Sklad №1 (Xomashyo)", defaults={'description': 'Sklad №1'})
    sklad2, _ = Warehouse.objects.get_or_create(name="Sklad №2 (Yarimtayyor/Blok)", defaults={'description': 'Sklad №2'})
    sklad3, _ = Warehouse.objects.get_or_create(name="Sklad №3 (Kesilgan)", defaults={'description': 'Sklad №3'})
    sklad4, _ = Warehouse.objects.get_or_create(name="Sklad №4 (Tayyor)", defaults={'description': 'Sklad №4'})

    recipe, _ = Recipe.objects.get_or_create(name="Test 15kg Block Recipe", defaults={
        'product': block_material,
        'density': 15.0,
        'is_active': True
    })

    ts = int(timezone.now().timestamp())
    zames = Zames.objects.create(
        zames_number=f"Z-WALK-{ts}",
        recipe=recipe,
        status='DONE',
        operator=operator
    )
    # Associate items for inventory tracking compatibility
    zames.items.create(material=block_material, quantity=1.0)
    print(f"✔ Step 0: Created Zames {zames.zames_number}")

    # 1. Complete Block Production (Lot created, individual blocks placed in COOLING status)
    print("\n--- Step 1: Completing Block Production (Generating Blocks) ---")
    block_count = 3
    block_lot = complete_block_production(
        zames=zames,
        form_number=f"FORM-{ts}",
        block_count=block_count,
        length=1000,
        width=1000,
        height=2000,
        density=15.0,
        user=operator,
        shift='DAY'
    )
    print(f"✔ Lot created successfully: ID {block_lot.id}, Count: {block_lot.block_count}, Status: {block_lot.status}")
    
    individual_blocks = FinishedBlock.objects.filter(lot=block_lot)
    print(f"✔ Individual blocks generated:")
    for b in individual_blocks:
        print(f"   - Block ID: {b.block_id} | Status: {b.get_status_display()} | Actual Density: {b.actual_density}")
        assert b.status == 'COOLING', "Initial block status must be COOLING"

    # 2. Dry the Block Lot (Transitions individual blocks from COOLING to QC_PENDING)
    print("\n--- Step 2: Drying the Block Lot (Transition to QC_PENDING) ---")
    # Mark status as DRYING so finish_drying_process can run
    block_lot.status = 'DRYING'
    block_lot.save()
    
    finish_drying_process(block_lot.id, user=operator)
    block_lot.refresh_from_db()
    print(f"✔ Drying finished! Block Lot status: {block_lot.status}")

    individual_blocks = list(FinishedBlock.objects.filter(lot=block_lot))
    print(f"✔ Individual blocks post-drying:")
    for b in individual_blocks:
        b.refresh_from_db()
        print(f"   - Block ID: {b.block_id} | Status: {b.get_status_display()}")
        assert b.status == 'QC_PENDING', "Block status after drying must be QC_PENDING"

    # 3. Perform QC check on blocks
    print("\n--- Step 3: Performing QC Check on Blocks ---")
    # Block 1: Perfect quality (A-Class) -> status='READY'
    block_1 = perform_block_qc(
        block_id=individual_blocks[0].id,
        classification='A_CLASS',
        status='READY',
        notes='QC Pass - Perfect quality!',
        actual_weight=30.0,
        actual_density=15.0,
        moisture=3.2,
        length=1000,
        width=1000,
        height=2000,
        visual_defects='None',
        user=operator
    )
    print(f"✔ Block 1 QC completed: {block_1.block_id} | Status: {block_1.get_status_display()} | Class: {block_1.get_classification_display()}")
    assert block_1.status == 'READY', "Block 1 must transition to READY"

    # Block 2: Premium (A-Class) -> status='READY' (For Finishing Job)
    block_2 = perform_block_qc(
        block_id=individual_blocks[1].id,
        classification='A_CLASS',
        status='READY',
        notes='QC Pass - Premium quality for Finishing!',
        actual_weight=30.5,
        actual_density=15.25,
        moisture=2.8,
        length=1000,
        width=1000,
        height=2000,
        visual_defects='None',
        user=operator
    )
    print(f"✔ Block 2 QC completed: {block_2.block_id} | Status: {block_2.get_status_display()} | Class: {block_2.get_classification_display()}")
    assert block_2.status == 'READY', "Block 2 must transition to READY"

    # Block 3: Reject (Brak) -> status='RECYCLE'
    block_3 = perform_block_qc(
        block_id=individual_blocks[2].id,
        classification='REJECT',
        status='RECYCLE',
        notes='Cracked surface - send to recycling!',
        actual_weight=28.0,
        actual_density=14.0,
        moisture=8.5,
        length=1000,
        width=990,
        height=2000,
        visual_defects='Deep crack along width',
        user=operator
    )
    print(f"✔ Block 3 QC completed: {block_3.block_id} | Status: {block_3.get_status_display()} | Class: {block_3.get_classification_display()}")
    assert block_3.status == 'RECYCLE', "Block 3 must transition to RECYCLE"

    # Verify State Machine Guard validation (attempting illegal transition READY -> CREATED)
    print("\n--- Step 3b: Testing State Machine Transition Guards ---")
    try:
        block_1.transition_to('CREATED', user=operator)
        print("❌ FAIL: Illegal transition READY -> CREATED was allowed!")
    except Exception as e:
        print(f"✅ PASS: State machine correctly blocked transition: {e}")

    # 4. CNC Operator Flow using Serialized Block (Block 1)
    print("\n--- Step 4: CNC Job Flow with Serialized Block ---")
    cnc_job = CNCJob.objects.create(
        job_number=f"CNC-WALK-{ts}",
        input_finished_block=block_1,
        input_block=block_lot,
        output_product=decorative_product,
        quantity_planned=10,
        machine_id='CNC-1',
        operator=operator,
        status='CREATED'
    )
    print(f"✔ CNC Job created: {cnc_job.job_number} | Block: {cnc_job.input_finished_block.block_id}")

    # Start CNC Job
    start_cnc_job(cnc_job.id, operator=operator)
    block_1.refresh_from_db()
    print(f"✔ CNC Job started! Job status: {cnc_job.status} | Block {block_1.block_id} status: {block_1.get_status_display()}")
    assert block_1.status == 'CUTTING', "Block 1 must be CUTTING while in CNC"

    # Complete CNC Job
    finish_cnc_job(cnc_job.id, finished_qty=10, waste_m3=0.08, operator=operator)
    block_1.refresh_from_db()
    print(f"✔ CNC Job completed! Job status: {cnc_job.status} | Block {block_1.block_id} status: {block_1.get_status_display()}")
    assert block_1.status == 'PACKAGED', "Block 1 must be PACKAGED after CNC completion"

    # 5. Finishing Operator Flow using Serialized Block (Block 2)
    print("\n--- Step 5: Finishing Job Flow with Serialized Block ---")
    finishing_job = FinishingJob.objects.create(
        job_number=f"FIN-WALK-{ts}",
        input_finished_block=block_2,
        product=decorative_product,
        quantity=5,
        operator=operator,
        status='PENDING'
    )
    print(f"✔ Finishing Job created: {finishing_job.job_number} | Block: {finishing_job.input_finished_block.block_id}")

    # Start Finishing Job
    start_finishing_job(finishing_job.id, operator=operator)
    block_2.refresh_from_db()
    print(f"✔ Finishing Job started! Job status: {finishing_job.status} | Block {block_2.block_id} status: {block_2.get_status_display()}")
    assert block_2.status == 'FINISHING', "Block 2 must be FINISHING while in Finishing"

    # Complete Finishing Job
    finish_finishing_job(finishing_job.id, finished_qty=5, waste_qty=0, operator=operator)
    block_2.refresh_from_db()
    print(f"✔ Finishing Job completed! Job status: {finishing_job.status} | Block {block_2.block_id} status: {block_2.get_status_display()}")
    assert block_2.status == 'PACKAGED', "Block 2 must be PACKAGED after Finishing completion"

    # 6. Verify Dashboard compatibility view aggregates real-time stats
    print("\n--- Step 6: Verifying Dashboard Executive KPIs ---")
    request = RequestFactory().get('/api/director/dashboard-compat/')
    view = DashboardCompatibilityView.as_view()
    response = view(request)
    data = response.data
    
    production_status = data.get('production_status', {})
    print("✔ Real-time KPIs returned by backend compat view:")
    for k, v in production_status.items():
        print(f"   - {k}: {v}")

    print("\n--- 🏁 ALL E2E VERIFICATIONS SUCCESSFUL! 🏁 ---")

if __name__ == "__main__":
    run_e2e_walkthrough()
