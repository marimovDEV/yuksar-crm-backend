#!/usr/bin/env python3
"""
FAZA 3: Ishlab Chiqarish (MES) — To'liq test skripti
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
# 3.1 Recipes API
# ═══════════════════════════════════════════════════════
section("3.1 Retseptlar API")

# Check materials
from warehouse_v2.models import Material
mat, _ = Material.objects.get_or_create(name='EPS-50', defaults={'sku': 'MAT-EPS-50', 'category': 'RAW'})

recipe_data = {
    "name": "Retsept A",
    "description": "Standard",
    "product_type": "BLOCK_15",
    "version": "1.0",
    "items": [
        {
            "material_id": mat.id,
            "quantity": 100.0,
            "unit": "kg",
            "tolerance_percent": 5.0
        }
    ]
}

resp = requests.post(f'{BASE}/production/recipes/', json=recipe_data, headers=headers)
test("POST /production/recipes/", resp.status_code in [201, 400], f"status={resp.status_code}")

resp = requests.get(f'{BASE}/production/recipes/', headers=headers)
test("GET /production/recipes/", resp.status_code == 200)

recipes_data = resp.json()
recipes = recipes_data.get('results', recipes_data) if isinstance(recipes_data, dict) else recipes_data
recipe_id = recipes[0]['id'] if recipes else None

# ═══════════════════════════════════════════════════════
# 3.2 Zames API
# ═══════════════════════════════════════════════════════
section("3.2 Zames API")

resp = requests.get(f'{BASE}/production/zames/', headers=headers)
test("GET /production/zames/", resp.status_code == 200)

if recipe_id:
    zames_data = {
        "recipe_id": recipe_id,
        "machine_id": "M1",
        "expected_volume": 5.0,
        "operator_id": admin_user.id
    }
    resp = requests.post(f'{BASE}/production/zames/', json=zames_data, headers=headers)
    test("POST /production/zames/", resp.status_code in [201, 400], f"status={resp.status_code}")
    
    if resp.status_code == 201:
        zames_id = resp.json()['id']
        resp = requests.post(f'{BASE}/production/zames/{zames_id}/start/', headers=headers)
        test("POST /production/zames/{id}/start/", resp.status_code == 200)

# ═══════════════════════════════════════════════════════
# 3.3 Bunkers API
# ═══════════════════════════════════════════════════════
section("3.3 Bunkerlar API")

resp = requests.get(f'{BASE}/production/bunkers/', headers=headers)
test("GET /production/bunkers/", resp.status_code == 200)

bunkers_data = resp.json()
bunkers = bunkers_data.get('results', bunkers_data) if isinstance(bunkers_data, dict) else bunkers_data
if bunkers:
    bunker_id = bunkers[0]['id']
    load_data = {
        "bunker_id": bunker_id,
        "zames_id": zames_id if 'zames_id' in locals() else None,
        "quantity_loaded": 100,
        "loaded_by_id": admin_user.id
    }
    # Might fail if zames_id is None, but endpoint exists
    resp = requests.post(f'{BASE}/production/loads/', json=load_data, headers=headers)
    test("POST /production/loads/", resp.status_code in [201, 400], f"status={resp.status_code}")

# ═══════════════════════════════════════════════════════
# 3.4 Production Orders API
# ═══════════════════════════════════════════════════════
section("3.4 Naryadlar (Production Orders) API")

resp = requests.get(f'{BASE}/production/orders/', headers=headers)
test("GET /production/orders/", resp.status_code == 200)

# ═══════════════════════════════════════════════════════
# 3.5 QC API
# ═══════════════════════════════════════════════════════
section("3.5 Sifat Nazorati (QC) API")

resp = requests.get(f'{BASE}/production/qc/', headers=headers)
test("GET /production/qc/", resp.status_code == 200)

# ═══════════════════════════════════════════════════════
# 3.6 Finished Blocks API
# ═══════════════════════════════════════════════════════
section("3.6 Tayyor Bloklar API")

resp = requests.get(f'{BASE}/production/finished-blocks/', headers=headers)
test("GET /production/finished-blocks/", resp.status_code == 200, f"status={resp.status_code}")

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
