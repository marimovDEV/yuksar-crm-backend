import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()
import requests
from accounts.models import User
from rest_framework_simplejwt.tokens import RefreshToken

u = User.objects.get(username='test_admin')
token = str(RefreshToken.for_user(u).access_token)
resp = requests.get('http://127.0.0.1:8899/api/users/me/', headers={'Authorization': f'Bearer {token}'})
print(resp.json())
