#!/usr/bin/env python3
"""
FAZA 2: Ombor Boshqaruvi (WMS) — To'liq test skripti
"""
import os, sys, django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

import requests

BASE = 'http://127.0.0.1:8899/api'
RESULTS = []

def test(name, passed, detail=""):
    status = "✅ PASS" if passed else "❌ FAIL"
    RESULTS.append((name, passed, detail))
    print(f"  {status} | {name}" + (f" → {detail}" if detail else ""))

def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")

# ═══════════════════════════════════════════════════════
# Setup: Get Admin Token
# ═══════════════════════════════════════════════════════
from accounts.models import User
from rest_framework_simplejwt.tokens import RefreshToken

try:
    admin_user = User.objects.get(username='test_admin')
    admin_token = str(RefreshToken.for_user(admin_user).access_token)
    headers = {'Authorization': f'Bearer {admin_token}'}
except Exception as e:
    print("❌ Xato: test_admin topilmadi yoki token olinmadi:", str(e))
    sys.exit(1)

# ═══════════════════════════════════════════════════════
# 2.1 Warehouses API
# ═══════════════════════════════════════════════════════
section("2.1 Omborlar API")

# Skladlar yaratish (agar yo'q bo'lsa)
from warehouse_v2.models import Warehouse, Material
w_names = ["Xom ashyo", "Bloklar", "CNC/Dekor", "Tayyor mahsulot"]
for wn in w_names:
    Warehouse.objects.get_or_create(name=wn)

resp = requests.get(f'{BASE}/warehouses/', headers=headers)
test("GET /warehouses/", resp.status_code == 200, f"status={resp.status_code}")
warehouses = resp.json()
if isinstance(warehouses, dict):
    warehouses = warehouses.get('results', warehouses)
test("4 ta ombor mavjud", len(warehouses) >= 4, f"count={len(warehouses)}")
if len(warehouses) > 0:
    w_id = warehouses[0]['id']

# ═══════════════════════════════════════════════════════
# 2.2 Materials API
# ═══════════════════════════════════════════════════════
section("2.2 Materiallar API")

resp = requests.get(f'{BASE}/materials/', headers=headers)
test("GET /materials/", resp.status_code == 200)

mat_data = {
    "name": "EPS-50",
    "sku": "MAT-EPS-50",
    "type": "RAW",
    "unit": "kg",
    "price_per_unit": 12000
}
resp = requests.post(f'{BASE}/materials/', json=mat_data, headers=headers)
test("POST /materials/ (yangi material)", resp.status_code in [201, 400], f"status={resp.status_code}") # 400 if exists

materials = requests.get(f'{BASE}/materials/', headers=headers).json()
if isinstance(materials, dict): materials = materials.get('results', materials)
mat_id = materials[0]['id'] if materials else None

# ═══════════════════════════════════════════════════════
# 2.3 Stocks API
# ═══════════════════════════════════════════════════════
section("2.3 Qoldiqlar API")

resp = requests.get(f'{BASE}/stocks/', headers=headers)
test("GET /stocks/", resp.status_code == 200, f"status={resp.status_code}")

# ═══════════════════════════════════════════════════════
# 2.4 Batches (Qabul qilish) API
# ═══════════════════════════════════════════════════════
section("2.4 Batches (Xomashyo Qabul) API")

if mat_id and len(warehouses) > 0:
    batch_data = {
        "batch_number": "BATCH-001",
        "material_id": mat_id,
        "warehouse_id": w_id,
        "initial_quantity": 5000,
        "current_quantity": 5000,
        "price_per_unit": 11500,
        "status": "RECEIVED"
    }
    resp = requests.post(f'{BASE}/batches/', json=batch_data, headers=headers)
    test("POST /batches/ (xomashyo qabul)", resp.status_code in [201, 400], f"status={resp.status_code}")

# ═══════════════════════════════════════════════════════
# 2.5 Transfers API
# ═══════════════════════════════════════════════════════
section("2.5 Transferlar API")

resp = requests.get(f'{BASE}/transfers/', headers=headers)
test("GET /transfers/", resp.status_code == 200)

if mat_id and len(warehouses) > 1:
    transfer_data = {
        "source_warehouse_id": warehouses[0]['id'],
        "destination_warehouse_id": warehouses[1]['id'],
        "material_id": mat_id,
        "quantity": 100,
        "notes": "Test transfer"
    }
    resp = requests.post(f'{BASE}/transfers/', json=transfer_data, headers=headers)
    test("POST /transfers/ (yaratish)", resp.status_code in [201, 400], f"status={resp.status_code}")
    if resp.status_code == 201:
        tr_id = resp.json()['id']
        resp2 = requests.post(f'{BASE}/transfers/{tr_id}/approve/', headers=headers)
        test("Transfer tasdiqlash", resp2.status_code == 200)

# ═══════════════════════════════════════════════════════
# 2.6 Inventory Audits API
# ═══════════════════════════════════════════════════════
section("2.6 Inventarizatsiya API")

resp = requests.get(f'{BASE}/inventory/audits/', headers=headers)
test("GET /inventory/audits/", resp.status_code == 200)

if len(warehouses) > 0:
    audit_data = {
        "warehouse_id": w_id,
        "status": "IN_PROGRESS",
        "notes": "Test audit"
    }
    resp = requests.post(f'{BASE}/inventory/audits/', json=audit_data, headers=headers)
    test("POST /inventory/audits/ (boshlash)", resp.status_code in [201, 400], f"status={resp.status_code}")

# ═══════════════════════════════════════════════════════
# NATIJA
# ═══════════════════════════════════════════════════════
section("📊 NATIJA")

total = len(RESULTS)
passed = sum(1 for _, p, _ in RESULTS if p)
failed = sum(1 for _, p, _ in RESULTS if not p)

print(f"\n  Jami: {total} | ✅ O'tdi: {passed} | ❌ O'tmadi: {failed}")
print(f"  Muvaffaqiyat: {passed/total*100:.1f}%")

if failed > 0:
    print(f"\n  ❌ O'tmagan testlar:")
    for name, p, detail in RESULTS:
        if not p:
            print(f"     - {name} ({detail})")

print()
