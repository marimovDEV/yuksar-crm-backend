from rest_framework import permissions


def get_user_role_name(user):
    if not getattr(user, 'is_authenticated', False):
        return ''
    if getattr(user, 'role_obj', None):
        return user.role_obj.name or user.role or ''
    return user.role or ''


def has_any_role(user, *roles):
    return get_user_role_name(user) in roles

class IsSuperAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'SUPERADMIN')

class IsAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'SUPERADMIN', 'ADMIN')

class IsWarehouseOperator(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'Omborchi', 'SUPERADMIN', 'ADMIN', 'WAREHOUSE_OPERATOR')

class IsProductionOperator(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'Ishlab chiqarish ustasi', 'SUPERADMIN', 'ADMIN', 'PRODUCTION_OPERATOR')

class IsCNCOperator(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'CNC operatori', 'SUPERADMIN', 'ADMIN', 'CNC_OPERATOR')

class IsFinishingOperator(permissions.BasePermission):
    """Permission for Pardozlovchi role."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'Pardozlovchi', 'SUPERADMIN', 'ADMIN', 'FINISHING_OPERATOR')

class IsWasteOperator(permissions.BasePermission):
    """Permission for Chiqindi operatori role."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'Chiqindi operatori', 'SUPERADMIN', 'ADMIN', 'WASTE_OPERATOR')

class IsSalesManager(permissions.BasePermission):
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'Sotuv menejeri', 'SUPERADMIN', 'ADMIN', 'SALES_MANAGER')

class IsAdminOrSalesManager(permissions.BasePermission):
    def has_permission(self, request, view):
        return IsAdmin().has_permission(request, view) or IsSalesManager().has_permission(request, view)

class IsCourier(permissions.BasePermission):
    """Permission for Kuryer role."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user, 'Bosh Admin', 'Admin', 'Kuryer', 'SUPERADMIN', 'ADMIN', 'COURIER')

class IsAdminOrCourier(permissions.BasePermission):
    def has_permission(self, request, view):
        return IsAdmin().has_permission(request, view) or IsCourier().has_permission(request, view)

class IsProductionRelated(permissions.BasePermission):
    """Any production-related role: Usta, CNC, Pardozlovchi, Chiqindi."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user,
            'Bosh Admin', 'Admin', 'Omborchi',
            'Ishlab chiqarish ustasi', 'CNC operatori', 'Pardozlovchi', 'Chiqindi operatori',
            'SUPERADMIN', 'ADMIN', 'WAREHOUSE_OPERATOR',
            'PRODUCTION_OPERATOR', 'CNC_OPERATOR', 'FINISHING_OPERATOR', 'WASTE_OPERATOR'
        )


class IsDocumentOperator(permissions.BasePermission):
    """
    Users who can work with business documents:
    admin, warehouse, production-related, sales, and courier roles.
    """
    def has_permission(self, request, view):
        return (
            IsAdmin().has_permission(request, view)
            or IsWarehouseOperator().has_permission(request, view)
            or IsProductionRelated().has_permission(request, view)
            or IsSalesManager().has_permission(request, view)
            or IsCourier().has_permission(request, view)
        )


class IsAccountant(permissions.BasePermission):
    """Buxgalter role — Accounting access, reports, audit view, limited edit."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user,
            'Bosh Admin', 'Admin', 'Buxgalter',
            'SUPERADMIN', 'ADMIN', 'ACCOUNTANT'
        )


class IsFinanceManager(permissions.BasePermission):
    """Moliya boshqaruvchi — full finance and accounting access."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user,
            'Bosh Admin', 'Admin', 'Buxgalter', 'Moliya boshqaruvchi',
            'SUPERADMIN', 'ADMIN', 'ACCOUNTANT', 'FINANCE_MANAGER'
        )


class IsAdminOrAccountant(permissions.BasePermission):
    """Admin yoki Buxgalter — for accounting-related views."""
    def has_permission(self, request, view):
        return IsAdmin().has_permission(request, view) or IsAccountant().has_permission(request, view)


class IsDirector(permissions.BasePermission):
    """Direktor — read-only access to analytics, reports, alerts, KPI."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user,
            'Bosh Admin', 'Admin', 'Direktor',
            'SUPERADMIN', 'ADMIN', 'DIRECTOR'
        )


class IsAdminOrDirector(permissions.BasePermission):
    """Admin yoki Direktor — analytics, reports, alerts."""
    def has_permission(self, request, view):
        return IsAdmin().has_permission(request, view) or IsDirector().has_permission(request, view)


class IsAdminOrDirectorOrAccountant(permissions.BasePermission):
    """Admin, Direktor yoki Buxgalter — reports va analytics."""
    def has_permission(self, request, view):
        return (
            IsAdmin().has_permission(request, view)
            or IsDirector().has_permission(request, view)
            or IsAccountant().has_permission(request, view)
        )


class IsQualityController(permissions.BasePermission):
    """QC Inspektor — quality control access."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user,
            'Bosh Admin', 'Admin', 'QC inspektor', 'Sifat nazoratchi',
            'SUPERADMIN', 'ADMIN', 'QC_INSPECTOR'
        )


class IsTechnologist(permissions.BasePermission):
    """Texnolog — recipes, production data, QC access."""
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True
        return has_any_role(request.user,
            'Bosh Admin', 'Admin', 'Texnolog',
            'SUPERADMIN', 'ADMIN', 'TECHNOLOGIST'
        )


class IsProductionOrQCOrTechnologist(permissions.BasePermission):
    """Production, QC yoki Texnolog — ishlab chiqarish ma'lumotlariga ruxsat."""
    def has_permission(self, request, view):
        return (
            IsProductionRelated().has_permission(request, view)
            or IsQualityController().has_permission(request, view)
            or IsTechnologist().has_permission(request, view)
        )

