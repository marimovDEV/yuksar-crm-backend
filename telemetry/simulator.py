import os
import sys
import time
import random
import django
from django.utils import timezone

# Setup Django Environment
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from telemetry.models import PLCDevice, PLCTag, TelemetryHistorian
from alerts.models import Alert, AlertRule
from accounts.models import User

def get_or_create_rule(name, trigger_type, threshold):
    rule, _ = AlertRule.objects.get_or_create(
        trigger_type=trigger_type,
        defaults={'name': name, 'threshold': threshold}
    )
    return rule

def trigger_alert(rule, title, message, severity):
    # Check if there is an active unresolved alert with the same title to prevent spamming
    active = Alert.objects.filter(title=title, is_resolved=False).exists()
    if not active:
        Alert.objects.create(
            rule=rule,
            title=title,
            message=message,
            severity=severity
        )
        print(f"🚨 ALERT TRIGGERED: {title} ({severity})")

def setup_initial_telemetry():
    print("🔋 Setting up initial PLCDevices and PLCTags in database...")
    
    # 1. Prefoamer PV-1
    pv1, _ = PLCDevice.objects.get_or_create(
        name="Predvspenivatel PV-1 (Prefoamer)",
        defaults={'protocol': 'SIMULATOR', 'is_connected': True}
    )
    
    # 2. Block Molding BF-12
    bf12, _ = PLCDevice.objects.get_or_create(
        name="Blok-forma BF-12 (Molder)",
        defaults={'protocol': 'SIMULATOR', 'is_connected': True}
    )

    # 3. Aging Bunkers
    bunkers, _ = PLCDevice.objects.get_or_create(
        name="Aging Bunkers (Silos)",
        defaults={'protocol': 'SIMULATOR', 'is_connected': True}
    )

    # Prefoamer Tags
    PLCTag.objects.get_or_create(key="pv1_steam_pressure", defaults={
        'device': pv1, 'name': "Prefoamer Bug' Bosimi", 'address': 'HR_40001', 'data_type': 'FLOAT', 'unit': 'bar', 'current_value': 0.4
    })
    PLCTag.objects.get_or_create(key="pv1_chamber_temp", defaults={
        'device': pv1, 'name': "Prefoamer Kamera Harorati", 'address': 'HR_40002', 'data_type': 'FLOAT', 'unit': '°C', 'current_value': 98.5
    })
    PLCTag.objects.get_or_create(key="pv1_raw_load", defaults={
        'device': pv1, 'name': "Prefoamer Granul Yuklanishi", 'address': 'HR_40003', 'data_type': 'FLOAT', 'unit': 'kg', 'current_value': 15.0
    })

    # Molder Tags
    PLCTag.objects.get_or_create(key="bf12_steam_pressure", defaults={
        'device': bf12, 'name': "Molder Bug' Bosimi", 'address': 'HR_40011', 'data_type': 'FLOAT', 'unit': 'bar', 'current_value': 0.8
    })
    PLCTag.objects.get_or_create(key="bf12_chamber_temp", defaults={
        'device': bf12, 'name': "Molder Kamera Harorati", 'address': 'HR_40012', 'data_type': 'FLOAT', 'unit': '°C', 'current_value': 118.0
    })
    PLCTag.objects.get_or_create(key="bf12_vacuum_pressure", defaults={
        'device': bf12, 'name': "Molder Vakuum Bosimi", 'address': 'HR_40013', 'data_type': 'FLOAT', 'unit': 'bar', 'current_value': -0.3
    })

    # Bunker Humidity Tags
    for i in range(1, 5):
        PLCTag.objects.get_or_create(key=f"bunker_humidity_{i}", defaults={
            'device': bunkers, 'name': f"Bunker #{i} Namlik O'lchagich", 'address': f'HR_4002{i}', 'data_type': 'FLOAT', 'unit': '%', 'current_value': 45.0
        })

    print("✅ Initial Devices and Tags are configured!")

def run_simulation():
    setup_initial_telemetry()
    print("📡 Real-time telemetry generator running. Simulating live datchik values every 5 seconds...")

    # Load tags from database
    tags_by_key = {tag.key: tag for tag in PLCTag.objects.all()}

    # Create / Fetch alarm rules
    pressure_rule = get_or_create_rule("Yuqori bug' bosimi", 'COMPLIANCE_VIOLATION', 0.75)
    temp_rule = get_or_create_rule("Yuqori kamera harorati", 'COMPLIANCE_VIOLATION', 123.0)

    # Simulation Variables state
    pv1_cycle_phase = 0 # 0=loading, 1=steaming, 2=discharging
    pv1_step = 0
    bf12_cycle_phase = 0 # 0=steaming, 1=vacuum, 2=cooling
    bf12_step = 0

    while True:
        try:
            # 1. Simulate PV-1 Prefoamer Cycle (duration 45 seconds total)
            pv1_step += 1
            if pv1_step > 9:
                pv1_step = 0
                pv1_cycle_phase = (pv1_cycle_phase + 1) % 3

            # Set physics values based on cycle phase
            if pv1_cycle_phase == 0: # Raw loading
                p_val = round(random.uniform(0.0, 0.05), 3)
                t_val = round(random.uniform(40.0, 55.0), 1)
                l_val = round(random.uniform(14.8, 15.2), 2)
            elif pv1_cycle_phase == 1: # Steaming
                p_val = round(random.uniform(0.35, 0.68), 3)
                t_val = round(random.uniform(96.0, 104.5), 1)
                l_val = round(random.uniform(14.8, 15.2), 2)
                # Random pressure spike for alarm testing (5% chance)
                if random.random() < 0.05:
                    p_val = round(random.uniform(0.78, 0.85), 3)
                    trigger_alert(
                        pressure_rule, 
                        "PV-1 Bug' Bosimi Yuqori!", 
                        f"Predvspenivatel PV-1 uskunasida bosim me'yordan oshdi: {p_val} bar! Bug' klapanini zudlik bilan tekshiring.",
                        'CRITICAL'
                    )
            else: # Discharging / Emptying
                p_val = round(random.uniform(0.02, 0.1), 3)
                t_val = round(random.uniform(70.0, 85.0), 1)
                l_val = round(random.uniform(0.0, 0.5), 2)

            tags_by_key['pv1_steam_pressure'].current_value = p_val
            tags_by_key['pv1_chamber_temp'].current_value = t_val
            tags_by_key['pv1_raw_load'].current_value = l_val

            # 2. Simulate BF-12 Block Molder Cycle (duration 60 seconds total)
            bf12_step += 1
            if bf12_step > 12:
                bf12_step = 0
                bf12_cycle_phase = (bf12_cycle_phase + 1) % 3

            if bf12_cycle_phase == 0: # Steaming
                bf_p = round(random.uniform(0.75, 1.15), 3)
                bf_t = round(random.uniform(115.0, 122.5), 1)
                bf_v = round(random.uniform(-0.05, 0.0), 3)
                # Temp warning spike
                if random.random() < 0.05:
                    bf_t = round(random.uniform(124.0, 127.5), 1)
                    trigger_alert(
                        temp_rule, 
                        "BF-12 Harorati Kritik Darajada!", 
                        f"Blok-forma BF-12 uskunasi harorati me'yordan oshdi: {bf_t} °C! Suv sovutish tizimini faollashtiring.",
                        'CRITICAL'
                    )
            elif bf12_cycle_phase == 1: # Vacuum Extraction
                bf_p = round(random.uniform(0.1, 0.3), 3)
                bf_t = round(random.uniform(90.0, 105.0), 1)
                bf_v = round(random.uniform(-0.68, -0.45), 3)
            else: # Cooling Yard / Ready
                bf_p = round(random.uniform(0.0, 0.05), 3)
                bf_t = round(random.uniform(35.0, 50.0), 1)
                bf_v = round(random.uniform(-0.1, 0.0), 3)

            tags_by_key['bf12_steam_pressure'].current_value = bf_p
            tags_by_key['bf12_chamber_temp'].current_value = bf_t
            tags_by_key['bf12_vacuum_pressure'].current_value = bf_v

            # 3. Simulate Bunker Humidity Aging (slow decay over time)
            for i in range(1, 5):
                tag_key = f"bunker_humidity_{i}"
                curr = tags_by_key[tag_key].current_value
                # Slow evaporation
                curr -= random.uniform(0.05, 0.15)
                if curr < 12.0:
                    curr = random.uniform(62.0, 68.0) # Reset on batch replacement
                tags_by_key[tag_key].current_value = round(curr, 2)

            # 4. Save and log to Historian
            for key, tag in tags_by_key.items():
                tag.save()
                # Create historical chart log
                TelemetryHistorian.objects.create(
                    tag=tag,
                    value=tag.current_value
                )

            # Keep last 50 historical entries per tag to prevent DB bloat
            for key, tag in tags_by_key.items():
                old_ids = TelemetryHistorian.objects.filter(tag=tag).values_list('id', flat=True)[100:]
                if old_ids:
                    TelemetryHistorian.objects.filter(id__in=list(old_ids)).delete()

            print(f"📊 Live telemetry generated successfully at {timezone.now().strftime('%H:%M:%S')}")
            time.sleep(5)
            
        except Exception as e:
            print(f"❌ Error in simulation loop: {e}")
            time.sleep(5)

if __name__ == '__main__':
    run_simulation()
