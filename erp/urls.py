from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from documents.views import DocumentViewSet
from erp.monitoring import health_check
from inventory.views import InventoryBatchViewSet, InventoryMovementViewSet
from rest_framework.routers import DefaultRouter
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import UserViewSet, DepartmentViewSet, RoleViewSet, PermissionViewSet, TokenObtainPairView, RoleSummaryView
from accounts.compatibility import UserMeView
from warehouse_v2.views import (
    SupplierViewSet, MaterialViewSet, RawMaterialBatchViewSet,
    WarehouseViewSet, StockViewSet, WarehouseTransferViewSet,
    PurchaseOrderViewSet
)
from warehouse_v2.compatibility import (
    InventoryCompatibilityView, ProductCompatibilityView, DocumentCompatibilityView
)
from production_v2.views import (
    ZamesViewSet, BunkerViewSet, BunkerLoadViewSet,
    BlockProductionViewSet, DryingProcessViewSet, RecipeViewSet,
    ProductionOrderViewSet, ProductionPlanViewSet, QualityCheckViewSet,
    ProductionBatchViewSet, FinishedBlockViewSet
)
from production_v2.compatibility import ProductionTaskCompatibilityView
from cnc_v2.views import CNCJobViewSet, WasteProcessingViewSet
from sales_v2.views import CustomerViewSet, InvoiceViewSet, SaleItemViewSet, DeliveryViewSet
from common_v2.views import AuditLogViewSet, NotificationViewSet, UserGuideViewSet, SupportTicketViewSet, VideoTutorialViewSet
from common_v2.compatibility import DashboardCompatibilityView
from reports_v2.views import (
    RawMaterialReportView, ProductionEfficiencyView,
    WarehouseBalanceView, SalesReportView, GeneralAnalyticsView,
    ProfitabilityDetailView, ReportHistoryViewSet, EnterpriseXLSXExportView
)
from transactions.views import TransactionViewSet
from finishing_v2.views import FinishingJobViewSet
from waste_v2.views import WasteTaskViewSet, WasteCategoryViewSet
from transport.views import (
    DriverViewSet, TransportContractViewSet, WaybillViewSet,
    TripViewSet, DriverPaymentViewSet, FuelLogViewSet
)
from dealers.views import DealerViewSet
from leads.views import LeadViewSet
from payroll.views import PayrollViewSet
from pricing.views import PricingRuleViewSet
from transport.views import VehicleViewSet

router = DefaultRouter()
router.register(r'users', UserViewSet)
router.register(r'departments', DepartmentViewSet)
router.register(r'roles', RoleViewSet)
router.register(r'permissions', PermissionViewSet)
router.register(r'suppliers', SupplierViewSet)
router.register(r'materials', MaterialViewSet)
router.register(r'batches', RawMaterialBatchViewSet, basename='raw-material-batch')
router.register(r'warehouses', WarehouseViewSet, basename='warehouse')
router.register(r'stocks', StockViewSet, basename='stock')
router.register(r'warehouse/stocks', StockViewSet, basename='warehouse-stock-alias')
router.register(r'transfers', WarehouseTransferViewSet, basename='warehouse-transfer')
router.register(r'warehouse/transfers', WarehouseTransferViewSet, basename='warehouse-transfer-alias')
router.register(r'procurement/orders', PurchaseOrderViewSet, basename='purchase-order')
router.register(r'production/zames', ZamesViewSet)
router.register(r'production/recipes', RecipeViewSet)
router.register(r'production/bunkers', BunkerViewSet)
router.register(r'production/loads', BunkerLoadViewSet)
router.register(r'production/blocks', BlockProductionViewSet)
router.register(r'production/drying', DryingProcessViewSet)
router.register(r'production/qc', QualityCheckViewSet, basename='production-qc')
router.register(r'production/quality-checks', QualityCheckViewSet, basename='production-quality-checks')
router.register(r'production/batches', ProductionBatchViewSet, basename='production-batch')
router.register(r'production/plans', ProductionPlanViewSet)
router.register(r'production/orders', ProductionOrderViewSet)
router.register(r'production/finished-blocks', FinishedBlockViewSet)
router.register(r'sales/invoices', InvoiceViewSet)
router.register(r'sales/deliveries', DeliveryViewSet, basename='sales-delivery')
router.register(r'transport/drivers', DriverViewSet)
router.register(r'transport/contracts', TransportContractViewSet)
router.register(r'transport/waybills', WaybillViewSet)
router.register(r'transport/trips', TripViewSet)
router.register(r'transport/payments', DriverPaymentViewSet)
router.register(r'transport/fuel-logs', FuelLogViewSet)
router.register(r'cnc/jobs', CNCJobViewSet)
router.register(r'cnc/waste', WasteProcessingViewSet)
router.register(r'finishing/jobs', FinishingJobViewSet, basename='finishing')
router.register(r'waste/tasks', WasteTaskViewSet)
router.register(r'waste/categories', WasteCategoryViewSet)
router.register(r'reports/history', ReportHistoryViewSet, basename='report-history')
router.register(r'transactions', TransactionViewSet)
router.register(r'inventory/batches', InventoryBatchViewSet, basename='inventory-batch')
router.register(r'inventory/movements', InventoryMovementViewSet, basename='inventory-movement')
# Legacy/Compatibility aliases
router.register(r'clients', CustomerViewSet, basename='client-compat')
router.register(r'sales-orders', InvoiceViewSet, basename='sales-order-compat')
router.register(r'audit-logs', AuditLogViewSet)
router.register(r'notifications', NotificationViewSet, basename='notification')
router.register(r'user-guide', UserGuideViewSet, basename='user-guide')
router.register(r'support-tickets', SupportTicketViewSet, basename='support-tickets')
router.register(r'video-tutorials', VideoTutorialViewSet, basename='video-tutorials')
router.register(r'documents', DocumentViewSet)

# New modules
router.register(r'dealers', DealerViewSet, basename='dealer')
router.register(r'leads', LeadViewSet, basename='lead')
router.register(r'payroll', PayrollViewSet, basename='payroll')
router.register(r'pricing/rules', PricingRuleViewSet, basename='pricing-rule')

# Fleet aliases (map fleet/ → transport/ for frontend compatibility)
router.register(r'fleet/drivers', DriverViewSet, basename='fleet-driver')
router.register(r'fleet/trips', TripViewSet, basename='fleet-trip')
router.register(r'fleet/vehicles', VehicleViewSet, basename='fleet-vehicle')
router.register(r'transport/vehicles', VehicleViewSet, basename='transport-vehicle')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', health_check, name='health'),
    path('api/users/me/', UserMeView.as_view(), name='user-me'),
    path('api/role-summary/', RoleSummaryView.as_view(), name='role-summary'),
    path('api/', include(router.urls)),
    
    # Compatibility Routes
    path('api/dashboard/summary/', DashboardCompatibilityView.as_view(), name='dashboard-summary'),
    # path('api/inventory/', InventoryCompatibilityView.as_view(), name='inventory-compat'), # Removed compatibility
    path('api/products/', ProductCompatibilityView.as_view(), name='product-compat'),
    # path('api/documents/', DocumentCompatibilityView.as_view(), name='document-compat'), # Removed compatibility
    path('api/production-tasks/', ProductionTaskCompatibilityView.as_view(), name='production-tasks'),
    path('api/production-tasks/<int:pk>/', ProductionTaskCompatibilityView.as_view(), name='production-tasks-detail'),
    
    # Reports
    path('api/reports/analytics/', GeneralAnalyticsView.as_view(), name='report-analytics'),
    path('api/reports/intake/', RawMaterialReportView.as_view(), name='report-intake'),
    path('api/reports/efficiency/', ProductionEfficiencyView.as_view(), name='report-efficiency'),
    path('api/reports/balances/', WarehouseBalanceView.as_view(), name='report-balances'),
    path('api/reports/sales/', SalesReportView.as_view(), name='report-sales'),
    path('api/reports/profitability/', ProfitabilityDetailView.as_view(), name='report-profitability'),
    path('api/reports/export/xlsx/', EnterpriseXLSXExportView.as_view(), name='report-export-xlsx'),

    # New Modules
    path('api/finance/', include('finance_v2.urls')),
    path('api/sales/', include('sales_v2.urls')),
    path('api/accounting/', include('accounting.urls')),
    path('api/budgets/', include('budgets.urls')),
    path('api/compliance/', include('compliance.urls')),
    path('api/alerts/', include('alerts.urls')),

    # Auth
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]

urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
