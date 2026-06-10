import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from accounts.models import User, ERPRole

u = User.objects.get(username='test_admin')
u.full_name = 'Test Admin'
u.role = 'Bosh Admin'
u.role_obj, _ = ERPRole.objects.get_or_create(name='Bosh Admin')
u.save()

print("User fixed.")
