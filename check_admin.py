import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from accounts.models import User
from accounts.serializers import UserSerializer

u = User.objects.get(username='test_admin')
data = UserSerializer(u).data
print("effective_role:", data.get('effective_role'))
print("role_display:", data.get('role_display'))
print("full_name:", data.get('full_name'))
print("first_name:", u.first_name)
print("last_name:", u.last_name)
