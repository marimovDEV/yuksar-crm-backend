from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings

class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "Department"
        verbose_name_plural = "Departments"

class ERPPermission(models.Model):
    name = models.CharField(max_length=100)
    key = models.CharField(max_length=100, unique=True) # e.g. "production.start"

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "ERP Permission"
        verbose_name_plural = "ERP Permissions"

class ERPRole(models.Model):
    name = models.CharField(max_length=100, unique=True)
    permissions = models.ManyToManyField(ERPPermission, blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = "ERP Role"
        verbose_name_plural = "ERP Roles"

class User(AbstractUser):
    STATUS_CHOICES = (
        ('ACTIVE', 'Active'),
        ('BLOCKED', 'Blocked'),
        ('PENDING', 'Pending'),
        ('RESIGNED', 'Resigned'),
        ('VACATION', 'Vacation'),
    )
    
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, unique=True)
    
    # RBAC Fields
    role_obj = models.ForeignKey(ERPRole, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    custom_permissions = models.ManyToManyField(ERPPermission, blank=True, related_name='custom_users')
    
    # Extended Profile
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE')
    start_date = models.DateField(null=True, blank=True)
    pin_code = models.CharField(max_length=20, unique=True, null=True, blank=True)
    telegram_id = models.CharField(max_length=100, blank=True)
    is_2fa = models.BooleanField(default=False)
    
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='users')
    assigned_warehouses = models.ManyToManyField('warehouse_v2.Warehouse', blank=True, related_name='assigned_users')
    
    # Shifts and Machines (Enterprise Requirements)
    shift = models.CharField(max_length=50, blank=True, null=True)
    assigned_machine = models.CharField(max_length=100, blank=True, null=True)
    must_change_password = models.BooleanField(default=False)
    
    # Additional Metadata
    notes = models.TextField(blank=True)
    last_login_ip = models.GenericIPAddressField(null=True, blank=True)
    
    # Legacy role field (kept for compatibility during migration, will be deprecated)
    role = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return f"{self.full_name} ({self.username})"

    @property
    def all_permissions(self) -> list:
        """Returns union of role permissions and custom overrides."""
        perms = set()
        if self.role_obj:
            for p in self.role_obj.permissions.all():
                perms.add(p.key)
        for p in self.custom_permissions.all():
            perms.add(p.key)
        return list(perms)
