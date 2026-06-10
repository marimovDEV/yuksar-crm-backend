#!/usr/bin/env python3
"""
FAZA 1: Authentication & RBAC — To'liq test skripti
Barcha API endpointlarini test qiladi
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
# 1. Avval test admin user yaratamiz
# ═══════════════════════════════════════════════════════
section("🔧 Test userlarni tayyorlash")

from accounts.models import User, ERPRole, Department
from django.db import IntegrityError

# Rollar
roles_needed = [
    'Bosh Admin', 'Direktor', 'Omborchi', 'Ishlab chiqarish ustasi',
    'CNC operatori', 'Sifat nazoratchisi', 'Buxgalter', 'Kuryer',
    'Texnolog', 'Servis muhandisi', 'Pardozlovchi', 'Chiqindi operatori',
    'Sotuv menejeri'
]
for rname in roles_needed:
    ERPRole.objects.get_or_create(name=rname)
print(f"  ℹ️  {ERPRole.objects.count()} ta rol mavjud")

# Bo'limlar
depts_needed = ['Boshqaruv', 'Ombor', 'Ishlab chiqarish', 'CNC', 'Pardozlash',
                'Chiqindi', 'Sotuv', 'Logistika', 'Moliya', 'Buxgalteriya', 'Texnologiya', 'Servis']
for dname in depts_needed:
    Department.objects.get_or_create(name=dname)
print(f"  ℹ️  {Department.objects.count()} ta bo'lim mavjud")

# Admin user
admin_user, created = User.objects.get_or_create(
    username='test_admin',
    defaults={
        'full_name': 'Test Admin',
        'phone': '+998990001122',
        'is_superuser': True,
        'is_staff': True,
        'role': 'Bosh Admin',
        'role_obj': ERPRole.objects.get(name='Bosh Admin'),
        'status': 'ACTIVE',
    }
)
admin_user.set_password('admin123')
admin_user.save()
print(f"  ℹ️  Admin user: test_admin (created={created})")

# Test users for each role
test_users = {
    'test_warehouse': ('Omborchi', 'Test Omborchi', '+998990001133'),
    'test_operator': ('Ishlab chiqarish ustasi', 'Test Operator', '+998990001144'),
    'test_cnc': ('CNC operatori', 'Test CNC', '+998990001155'),
    'test_qc': ('Sifat nazoratchisi', 'Test QC', '+998990001166'),
    'test_sales': ('Sotuv menejeri', 'Test Sales', '+998990001177'),
    'test_accounting': ('Buxgalter', 'Test Buxgalter', '+998990001188'),
    'test_logistics': ('Kuryer', 'Test Kuryer', '+998990001199'),
    'test_technologist': ('Texnolog', 'Test Texnolog', '+998990001200'),
    'test_maintenance': ('Servis muhandisi', 'Test Servis', '+998990001211'),
    'test_finishing': ('Pardozlovchi', 'Test Pardoz', '+998990001222'),
    'test_waste': ('Chiqindi operatori', 'Test Chiqindi', '+998990001233'),
    'test_director': ('Direktor', 'Test Direktor', '+998990001244'),
}

for uname, (role_name, fname, phone) in test_users.items():
    role = ERPRole.objects.get(name=role_name)
    u, c = User.objects.get_or_create(
        username=uname,
        defaults={
            'full_name': fname,
            'phone': phone,
            'role': role_name,
            'role_obj': role,
            'status': 'ACTIVE',
        }
    )
    u.set_password('test123')
    u.save()

print(f"  ℹ️  {User.objects.count()} ta foydalanuvchi mavjud")

# ═══════════════════════════════════════════════════════
# 2. Login API Testlari
# ═══════════════════════════════════════════════════════
section("1.1 Login API Testlari")

# Test 1: To'g'ri login
resp = requests.post(f'{BASE}/token/', json={'username': 'test_admin', 'password': 'admin123'})
test("Login (to'g'ri parol)", resp.status_code == 200, f"status={resp.status_code}")
tokens = resp.json() if resp.status_code == 200 else {}
admin_token = tokens.get('access', '')
test("Access token qaytdi", bool(admin_token), f"len={len(admin_token)}")
test("Refresh token qaytdi", bool(tokens.get('refresh', '')))

# Test 2: Noto'g'ri parol
resp = requests.post(f'{BASE}/token/', json={'username': 'test_admin', 'password': 'wrong_pass'})
test("Login (noto'g'ri parol → 401)", resp.status_code == 401, f"status={resp.status_code}")

# Test 3: Mavjud bo'lmagan user
resp = requests.post(f'{BASE}/token/', json={'username': 'nonexistent', 'password': 'test'})
test("Login (mavjud bo'lmagan user → 401)", resp.status_code == 401)

# Test 4: Token refresh
if tokens.get('refresh'):
    resp = requests.post(f'{BASE}/token/refresh/', json={'refresh': tokens['refresh']})
    test("Token refresh", resp.status_code == 200, f"status={resp.status_code}")
    new_access = resp.json().get('access', '')
    test("Yangi access token qaytdi", bool(new_access))

# ═══════════════════════════════════════════════════════
# 3. Users/Me API
# ═══════════════════════════════════════════════════════
section("1.2 Users/Me API")

headers = {'Authorization': f'Bearer {admin_token}'}
resp = requests.get(f'{BASE}/users/me/', headers=headers)
test("GET /users/me/ — 200", resp.status_code == 200, f"status={resp.status_code}")
if resp.status_code == 200:
    me = resp.json()
    test("username to'g'ri", me.get('username') == 'test_admin', me.get('username'))
    test("is_superuser=True", me.get('is_superuser') == True)
    test("effective_role mavjud", bool(me.get('effective_role') or me.get('role_display')))
    test("full_name mavjud", bool(me.get('full_name')))

# Test: Unauthorized request (no token)
resp = requests.get(f'{BASE}/users/me/')
test("Users/me tokensiz → 401", resp.status_code == 401)

# ═══════════════════════════════════════════════════════
# 4. Users List API
# ═══════════════════════════════════════════════════════
section("1.3 Users / Roles / Departments API")

resp = requests.get(f'{BASE}/users/', headers=headers)
test("GET /users/ — 200", resp.status_code == 200, f"status={resp.status_code}")
if resp.status_code == 200:
    users = resp.json()
    if isinstance(users, dict):
        users = users.get('results', users)
    test("Users ro'yxati bo'sh emas", len(users) > 0, f"count={len(users)}")

resp = requests.get(f'{BASE}/roles/', headers=headers)
test("GET /roles/ — 200", resp.status_code == 200)
if resp.status_code == 200:
    roles = resp.json()
    if isinstance(roles, dict):
        roles = roles.get('results', roles)
    test("Rollar ro'yxati 10+ ta", len(roles) >= 10, f"count={len(roles)}")

resp = requests.get(f'{BASE}/departments/', headers=headers)
test("GET /departments/ — 200", resp.status_code == 200)
if resp.status_code == 200:
    depts = resp.json()
    if isinstance(depts, dict):
        depts = depts.get('results', depts)
    test("Bo'limlar ro'yxati 10+ ta", len(depts) >= 10, f"count={len(depts)}")

# ═══════════════════════════════════════════════════════
# 5. Role-based login test (har bir test user login bo'lishi)
# ═══════════════════════════════════════════════════════
section("1.4 Rol-bo'yicha Login Tekshiruvi")

for uname, (role_name, fname, phone) in test_users.items():
    resp = requests.post(f'{BASE}/token/', json={'username': uname, 'password': 'test123'})
    if resp.status_code == 200:
        t = resp.json()['access']
        h = {'Authorization': f'Bearer {t}'}
        me_resp = requests.get(f'{BASE}/users/me/', headers=h)
        if me_resp.status_code == 200:
            me = me_resp.json()
            effective = me.get('effective_role') or me.get('role_display') or me.get('role', '')
            test(f"{role_name} login + /me/", True, f"role={effective}")
        else:
            test(f"{role_name} /me/ xato", False, f"status={me_resp.status_code}")
    else:
        test(f"{role_name} login", False, f"status={resp.status_code}")

# ═══════════════════════════════════════════════════════
# 6. Password change test
# ═══════════════════════════════════════════════════════
section("1.5 Parol O'zgartirish")

# Test user yaratamiz must_change_password=True bilan
pwd_user, _ = User.objects.get_or_create(
    username='test_pwd_change',
    defaults={
        'full_name': 'Pwd Change Test',
        'phone': '+998990009999',
        'role': 'Omborchi',
        'role_obj': ERPRole.objects.get(name='Omborchi'),
        'status': 'ACTIVE',
        'must_change_password': True,
    }
)
pwd_user.set_password('temp123')
pwd_user.save()

resp = requests.post(f'{BASE}/token/', json={'username': 'test_pwd_change', 'password': 'temp123'})
test("Temp user login", resp.status_code == 200)
if resp.status_code == 200:
    tk = resp.json()['access']
    h = {'Authorization': f'Bearer {tk}'}
    me = requests.get(f'{BASE}/users/me/', headers=h).json()
    test("must_change_password=True", me.get('must_change_password') == True)
    
    # Parolni o'zgartirish
    resp = requests.patch(f'{BASE}/users/me/', json={
        'password': 'newpass123',
        'must_change_password': False
    }, headers=h)
    test("Parol o'zgartirish", resp.status_code == 200, f"status={resp.status_code}")

# ═══════════════════════════════════════════════════════
# 7. Impersonate test
# ═══════════════════════════════════════════════════════
section("1.6 Impersonate (Foydalanuvchi nomidan kirish)")

target_user = User.objects.filter(username='test_sales').first()
if target_user:
    resp = requests.post(f'{BASE}/users/{target_user.id}/impersonate/', headers=headers)
    test("Impersonate API", resp.status_code == 200, f"status={resp.status_code}")
    if resp.status_code == 200:
        imp_token = resp.json().get('access', '')
        h2 = {'Authorization': f'Bearer {imp_token}'}
        me = requests.get(f'{BASE}/users/me/', headers=h2).json()
        test("Impersonated user = test_sales", me.get('username') == 'test_sales', me.get('username'))

# ═══════════════════════════════════════════════════════
# 8. RBAC: Non-admin user cannot access admin endpoints
# ═══════════════════════════════════════════════════════
section("1.7 RBAC — Ruxsat Tekshiruvi")

# Sales user tries to access /users/ (admin-only)
resp = requests.post(f'{BASE}/token/', json={'username': 'test_sales', 'password': 'test123'})
if resp.status_code == 200:
    sales_token = resp.json()['access']
    h_sales = {'Authorization': f'Bearer {sales_token}'}
    
    resp = requests.get(f'{BASE}/users/', headers=h_sales)
    test("Sales user → /users/ ruxsat yo'q (403)", resp.status_code == 403, f"status={resp.status_code}")
    
    resp = requests.get(f'{BASE}/roles/', headers=h_sales)
    test("Sales user → /roles/ ruxsat yo'q (403)", resp.status_code == 403, f"status={resp.status_code}")

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
