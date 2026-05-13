import os
import sys
import django

# Setup Django environment
sys.path.append('.')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from accounts.models import User, ERPRole

# Ensure SUPERADMIN role exists (it should after seeding)
role_obj, _ = ERPRole.objects.get_or_create(name='SUPERADMIN')

# Create/Update admin user
username = 'admin'
password = 'admin'

user, created = User.objects.get_or_create(username=username)
user.set_password(password)
user.is_superuser = True
user.is_staff = True
user.role = 'SUPERADMIN'
user.role_obj = role_obj
user.full_name = 'Bosh Admin'
if not user.phone:
    user.phone = '998900000000'
user.status = 'ACTIVE'
user.save()

if created:
    print(f"User '{username}' created successfully with password '{password}'")
else:
    print(f"User '{username}' updated successfully with password '{password}'")
