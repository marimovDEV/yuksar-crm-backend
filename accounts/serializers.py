from rest_framework import serializers
from .models import User, ERPPermission, ERPRole, Department
from warehouse_v2.models import Warehouse
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer as SimpleJWTTokenSerializer
from rest_framework_simplejwt.tokens import RefreshToken

class DepartmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Department
        fields = ('id', 'name', 'description')

class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ERPPermission
        fields = ('id', 'name', 'key')

class RoleSerializer(serializers.ModelSerializer):
    permissions_detail = PermissionSerializer(source='permissions', many=True, read_only=True)
    permission_ids = serializers.PrimaryKeyRelatedField(
        source='permissions',
        queryset=ERPPermission.objects.all(),
        many=True,
        write_only=True
    )

    class Meta:
        model = ERPRole
        fields = ('id', 'name', 'permissions', 'permissions_detail', 'permission_ids')
        extra_kwargs = {'permissions': {'read_only': True}}

class UserSerializer(serializers.ModelSerializer):
    role_display = serializers.SerializerMethodField()
    effective_role = serializers.SerializerMethodField()
    responsibility_summary = serializers.SerializerMethodField()
    task_scope = serializers.SerializerMethodField()
    assigned_warehouse_names = serializers.SerializerMethodField()
    all_permissions = serializers.ReadOnlyField()
    role_id = serializers.PrimaryKeyRelatedField(
        source='role_obj',
        queryset=ERPRole.objects.all(),
        required=False,
        allow_null=True
    )
    role_detail = RoleSerializer(source='role_obj', read_only=True)
    department_id = serializers.PrimaryKeyRelatedField(
        source='department',
        queryset=Department.objects.all(),
        required=False,
        allow_null=True
    )
    department_name = serializers.ReadOnlyField(source='department.name')
    assigned_warehouses = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Warehouse.objects.all(), required=False
    )
    custom_permissions = serializers.SlugRelatedField(
        many=True,
        slug_field='key',
        queryset=ERPPermission.objects.all(),
        required=False
    )
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'full_name', 'phone', 'email', 
            'role', 'role_id', 'role_detail', 'role_display', 'effective_role', 'all_permissions',
            'status', 'start_date', 'pin_code', 'telegram_id', 'is_2fa',
            'department', 'department_id', 'department_name',
            'assigned_warehouses', 'assigned_warehouse_names',
            'responsibility_summary', 'task_scope',
            'shift', 'assigned_machine', 'must_change_password', 'custom_permissions',
            'notes', 'last_login_ip', 'password',
            'is_superuser', 'is_staff'
        ]
        extra_kwargs = {'password': {'write_only': True}}

    def get_role_display(self, obj):
        if obj.role_obj:
             return obj.role_obj.name
        return obj.role

    def get_effective_role(self, obj):
        return self.get_role_display(obj)

    def get_assigned_warehouse_names(self, obj):
        return list(obj.assigned_warehouses.values_list('name', flat=True))

    def get_responsibility_summary(self, obj):
        role = self.get_effective_role(obj)
        summaries = {
            'Bosh Admin': "Tizim bo'ylab to'liq boshqaruv, nazorat va konfiguratsiya.",
            'Admin': "Operatsion boshqaruv, xodimlar, hujjatlar va jarayon nazorati.",
            'Omborchi': "Sklad kirim-chiqimi, transferlar va qoldiq nazorati.",
            'Ishlab chiqarish ustasi': "Zames, quritish, formovka va ishlab chiqarish oqimini boshqarish.",
            'CNC operatori': "Kesish buyurtmalari va CNC ishlab chiqarish vazifalari.",
            'Pardozlovchi': "Armirlash, shpaklyovka va tayyor dekor jarayonlari.",
            'Chiqindi operatori': "Chiqindi qabul qilish, qayta ishlash va yo'qotish nazorati.",
            'Sotuv menejeri': "Mijozlar, invoice, yetkazib berish va sotuv yakunlash.",
            'Kuryer': "Waybill, yetkazib berish va topshirish tasdiqlari.",
        }
        return summaries.get(role, "Rol bo'yicha vazifalar hali aniqlanmagan.")

    def get_task_scope(self, obj):
        role = self.get_effective_role(obj)
        task_map = {
            'Bosh Admin': ['staff.manage', 'permissions.manage', 'reports.view', 'system.audit'],
            'Admin': ['operations.manage', 'documents.manage', 'reports.view', 'staff.view'],
            'Omborchi': ['warehouse.receive', 'warehouse.transfer', 'stock.check', 'documents.confirm'],
            'Ishlab chiqarish ustasi': ['production.plan', 'stage.start', 'stage.complete', 'quality.track'],
            'CNC operatori': ['cnc.start', 'cnc.finish', 'warehouse3.consume'],
            'Pardozlovchi': ['finishing.start', 'finishing.finish', 'warehouse4.fill'],
            'Chiqindi operatori': ['waste.accept', 'waste.process', 'waste.report'],
            'Sotuv menejeri': ['sales.create', 'sales.confirm', 'delivery.manage', 'clients.manage'],
            'Kuryer': ['delivery.pickup', 'delivery.complete', 'documents.scan'],
        }
        return task_map.get(role, [])

    def _sync_legacy_role(self, validated_data):
        role_obj = validated_data.get('role_obj')
        if role_obj:
            validated_data['role'] = role_obj.name
        elif 'role' in validated_data and not validated_data.get('role'):
            validated_data['role'] = ''

    def create(self, validated_data):
        assigned_warehouses = validated_data.pop('assigned_warehouses', [])
        custom_permissions = validated_data.pop('custom_permissions', [])
        password = validated_data.pop('password', None)
        self._sync_legacy_role(validated_data)
        user = User.objects.create(**validated_data)
        if assigned_warehouses:
            user.assigned_warehouses.set(assigned_warehouses)
        if custom_permissions:
            user.custom_permissions.set(custom_permissions)
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])
        return user

    def update(self, instance, validated_data):
        assigned_warehouses = validated_data.pop('assigned_warehouses', None)
        custom_permissions = validated_data.pop('custom_permissions', None)
        password = validated_data.pop('password', None)
        self._sync_legacy_role(validated_data)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if 'role_obj' in validated_data and validated_data.get('role_obj') is None and 'role' not in validated_data:
            instance.role = ''
        if password:
            instance.set_password(password)
        instance.save()
        if assigned_warehouses is not None:
            instance.assigned_warehouses.set(assigned_warehouses)
        if custom_permissions is not None:
            instance.custom_permissions.set(custom_permissions)
        return instance

class TokenObtainPairSerializer(SimpleJWTTokenSerializer):
    def validate(self, attrs):
        return super().validate(attrs)

def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }
