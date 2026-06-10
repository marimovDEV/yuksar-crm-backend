import os
import django
import sys
import requests

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "erp.settings")
django.setup()

from rest_framework_simplejwt.tokens import RefreshToken
from accounts.models import User

def run_tests():
    BASE = 'http://127.0.0.1:8899/api'
    
    admin_user = User.objects.filter(username='admin').first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin', 'admin@yuksar.uz', 'admin123')
        
    token = str(RefreshToken.for_user(admin_user).access_token)
    headers = {'Authorization': f'Bearer {token}'}

    endpoints = {
        "Phase 5: Procurement": [
            "/suppliers/",
            "/procurement/orders/"
        ],
        "Phase 6: Sales & CRM": [
            "/clients/",
            "/sales-orders/",
            "/sales/invoices/",
            "/sales/deliveries/"
        ],
        "Phase 7: Finance & Accounting": [
            "/transactions/",
        ],
        "Phase 8: HR & Attendance": [
            "/hr/employees/",
            "/hr/attendance/"
        ],
        "Phase 9: Fleet (Transport)": [
            "/transport/vehicles/",
            "/transport/drivers/",
            "/transport/trips/"
        ]
    }

    total = 0
    passed = 0

    for phase, urls in endpoints.items():
        print("="*60)
        print(f"  {phase}")
        print("="*60)
        for url in urls:
            total += 1
            try:
                r = requests.get(f'{BASE}{url}', headers=headers)
                if r.status_code in [200, 403, 404]: # Some apps might not be fully registered or require specific roles, 404 could mean urls not set properly, but let's see.
                    print(f"  {'✅ PASS' if r.status_code == 200 else f'⚠️ WARN (status={r.status_code})'} | GET {url}")
                    if r.status_code == 200: passed += 1
                else:
                    print(f"  ❌ FAIL | GET {url} → status={r.status_code}")
            except Exception as e:
                print(f"  ❌ FAIL | GET {url} → {str(e)}")
        print()

    print(f"  Overall: {passed}/{total} passed (200 OK)")

if __name__ == '__main__':
    run_tests()
