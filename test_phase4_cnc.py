import os
import django
import sys
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "erp.settings")
django.setup()

from accounts.models import User
from rest_framework_simplejwt.tokens import RefreshToken
import requests

def run_tests():
    BASE = 'http://127.0.0.1:8899/api'
    
    admin_user = User.objects.filter(username='admin').first()
    if not admin_user:
        admin_user = User.objects.create_superuser('admin', 'admin@yuksar.uz', 'admin123')
        
    token = str(RefreshToken.for_user(admin_user).access_token)
    headers = {'Authorization': f'Bearer {token}'}

    print("="*60)
    print("  4.1 CNC API")
    print("="*60)
    
    # CNC Jobs
    r = requests.get(f'{BASE}/cnc/jobs/', headers=headers)
    print(f"  {'✅ PASS' if r.status_code == 200 else '❌ FAIL'} | GET /cnc/jobs/ → status={r.status_code}")
    
    # CNC Waste
    r = requests.get(f'{BASE}/cnc/waste/', headers=headers)
    print(f"  {'✅ PASS' if r.status_code == 200 else '❌ FAIL'} | GET /cnc/waste/ → status={r.status_code}")

    print("\n" + "="*60)
    print("  4.2 Finishing API")
    print("="*60)
    
    r = requests.get(f'{BASE}/finishing/jobs/', headers=headers)
    print(f"  {'✅ PASS' if r.status_code == 200 else '❌ FAIL'} | GET /finishing/jobs/ → status={r.status_code}")

    print("\n" + "="*60)
    print("  4.3 Waste Management API")
    print("="*60)
    
    r = requests.get(f'{BASE}/waste/tasks/', headers=headers)
    print(f"  {'✅ PASS' if r.status_code == 200 else '❌ FAIL'} | GET /waste/tasks/ → status={r.status_code}")

    r = requests.get(f'{BASE}/waste/categories/', headers=headers)
    print(f"  {'✅ PASS' if r.status_code == 200 else '❌ FAIL'} | GET /waste/categories/ → status={r.status_code}")

if __name__ == '__main__':
    run_tests()
