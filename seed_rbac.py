import os
import sys
import django

# Ensure project root is in path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'erp.settings')
django.setup()

from accounts.models import User, ERPRole, ERPPermission

def seed_rbac():
    # Define Comprehensive Permissions
    perms_data = [
        # Warehouse
        ('warehouse.view', "Omborni ko'rish"),
        ('warehouse.create', "Yangi mahsulot/kirim yaratish"),
        ('warehouse.move', "Mahsulot ko'chirish (transfer)"),
        ('warehouse.audit', "Inventarizatsiya dalolatnomalari"),
        ('warehouse.delete', "Ombor ma'lumotlarini o'chirish"),
        
        # Production
        ('production.start', "Ishlab chiqarishni boshlash"),
        ('production.stop', "Ishlab chiqarishni yakunlash"),
        ('production.writeoff', "Brak/Chiqindi hisobga olish"),
        ('production.recipe', "Retseptlar va BOM boshqaruvi"),
        ('production.qc', "Sifat nazorati (QC) tasdiqlash"),
        
        # Sales & CRM
        ('sales.view', "Sotuv va mijozlarni ko'rish"),
        ('sales.create', "Yangi sotuv rasmiylashtirish"),
        ('sales.crm', "Leadlar va CRM boshqaruvi"),
        ('sales.debt', "Qarzdorlik nazorati"),
        ('sales.delete', "Sotuvni bekor qilish"),
        
        # Finance
        ('finance.view', "Moliyaviy hisobotlarni ko'rish"),
        ('finance.transaction', "Kirim/Chiqim operatsiyalari"),
        ('finance.budget', "Byudjetlashtirish va limitlar"),
        ('finance.accounting', "Buxgalteriya o'tkazmalari"),
        
        # Logistics
        ('logistics.view', "Yetkazib berishlarni ko'rish"),
        ('logistics.manage', "Kuryer tayinlash va marshrutlar"),
        ('logistics.confirm', "Yuk topshirishni tasdiqlash"),
        
        # Admin & Reports
        ('reports.view', "Analitik hisobotlarni ko'rish"),
        ('reports.export', "Hisobotlarni eksport qilish (Excel/PDF)"),
        ('admin.users', "Xodimlarni boshqarish"),
        ('admin.config', "Tizim sozlamalari va audit"),
    ]

    perms = {}
    for key, name in perms_data:
        p, _ = ERPPermission.objects.get_or_create(key=key, defaults={'name': name})
        perms[key] = p

    # Define Detailed Roles based on User Guide
    roles_data = {
        'Bosh Admin': list(perms.keys()),
        'Admin': [
            'warehouse.view', 'warehouse.create', 'warehouse.move', 'warehouse.audit',
            'production.start', 'production.stop', 'production.writeoff', 'production.qc',
            'sales.view', 'sales.create', 'sales.crm', 'sales.debt',
            'finance.view', 'finance.transaction',
            'logistics.view', 'logistics.manage',
            'reports.view', 'reports.export',
            'admin.users'
        ],
        'Sotuv menejeri': [
            'sales.view', 'sales.create', 'sales.crm', 'sales.debt',
            'reports.view', 'warehouse.view'
        ],
        'Omborchi': [
            'warehouse.view', 'warehouse.create', 'warehouse.move', 'warehouse.audit'
        ],
        'Ishlab chiqarish ustasi': [
            'production.start', 'production.stop', 'production.writeoff', 
            'production.recipe', 'production.qc', 'warehouse.view'
        ],
        'CNC operatori': [
            'production.start', 'production.stop', 'production.writeoff'
        ],
        'Kuryer': [
            'logistics.view', 'logistics.confirm'
        ],
        'Buxgalter': [
            'finance.view', 'finance.transaction', 'finance.budget', 'finance.accounting',
            'reports.view', 'reports.export'
        ],
    }

    for role_name, p_keys in roles_data.items():
        role, _ = ERPRole.objects.get_or_create(name=role_name)
        role.permissions.set([perms[k] for k in p_keys])
        role.save()

    # Link existing users to roles
    for user in User.objects.all():
        if user.role:
            role_obj = ERPRole.objects.filter(name=user.role).first()
            if role_obj:
                user.role_obj = role_obj
                user.save()

if __name__ == "__main__":
    seed_rbac()
    print("RBAC Seeded successfully based on User Guide v2.4!")
