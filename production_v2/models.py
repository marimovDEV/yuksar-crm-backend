from django.db import models
from django.conf import settings
from common_v2.mixins import StateMachineMixin

class Recipe(models.Model):
    product = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE, related_name='recipes', null=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    density = models.FloatField(default=0, help_text="Target density for this recipe (kg/m3)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} for {self.product.name if self.product else '?'}"

class RecipeItem(models.Model):
    recipe = models.ForeignKey(Recipe, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    quantity = models.FloatField(help_text="Standard quantity for this recipe")

    def __str__(self):
        return f"{self.recipe.name}: {self.material.name} x {self.quantity}"

class ProductionBatch(StateMachineMixin, models.Model):
    batch_number = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=50, choices=(
        ('OPEN', 'Ochiq (Hisoblanmoqda)'),
        ('CLOSED', 'Yopilgan (Final)'),
        ('CANCELLED', 'Bekor qilingan'),
    ), default='OPEN')
    
    STATUS_TRANSITIONS = {
        'OPEN': ['CLOSED', 'CANCELLED'],
        'CLOSED': [],
        'CANCELLED': ['OPEN'],
    }
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    total_output_qty = models.FloatField(default=0, help_text="Total blocks or output units")
    
    # Costs
    material_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    energy_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    labor_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    overhead_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    cnc_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    
    cost_confidence = models.CharField(max_length=20, choices=(
        ('REAL', 'Haqiqiy (Kiritilgan)'),
        ('ESTIMATED', 'Taxminiy (Avto-Taqsimlangan)'),
    ), default='ESTIMATED')

    def __str__(self):
        return f"Batch {self.batch_number} ({self.status}) - Unit Cost: {self.unit_cost}"

class Zames(StateMachineMixin, models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('IN_PROGRESS', 'Jarayonda'),
        ('DONE', 'Tugallandi'),
        ('CANCELLED', 'Bekor qilindi'),
        ('FAILED', 'Xatolik / To‘xtagan'),
    )

    STATUS_TRANSITIONS = {
        'PENDING': ['IN_PROGRESS', 'CANCELLED'],
        'IN_PROGRESS': ['DONE', 'FAILED', 'CANCELLED'],
        'DONE': [],
        'FAILED': ['IN_PROGRESS', 'CANCELLED'],
        'CANCELLED': ['PENDING'],
    }

    production_batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='zames_list', null=True, blank=True)
    zames_number = models.CharField(max_length=50, unique=True)
    recipe = models.ForeignKey(Recipe, on_delete=models.SET_NULL, null=True, blank=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')
    
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    input_weight = models.FloatField(default=0)
    output_weight = models.FloatField(default=0)
    expanded_weight = models.FloatField(default=0, help_text="Weight after primary expansion") # legacy field placeholder
    dried_weight = models.FloatField(default=0) # legacy field placeholder
    
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    machine_id = models.CharField(max_length=50, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Zames {self.zames_number} ({self.status})"

class ZamesItem(models.Model):
    zames = models.ForeignKey(Zames, on_delete=models.CASCADE, related_name='items')
    material = models.ForeignKey('warehouse_v2.Material', on_delete=models.CASCADE)
    batch = models.ForeignKey('warehouse_v2.RawMaterialBatch', on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.FloatField()
    
    # Financials (Phase 12)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def __str__(self):
        return f"{self.zames}: {self.material.name} ({self.quantity})"

class Bunker(models.Model):
    name = models.CharField(max_length=50) # Bunker 1, 2, 3, 4
    is_occupied = models.BooleanField(default=False)
    last_occupied_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({'Occupied' if self.is_occupied else 'Free'})"

class BunkerLoad(models.Model):
    production_batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='bunker_loads', null=True, blank=True)
    zames = models.ForeignKey(Zames, on_delete=models.CASCADE, related_name='loads')
    bunker = models.ForeignKey(Bunker, on_delete=models.CASCADE, related_name='loads')
    load_time = models.DateTimeField(auto_now_add=True)
    required_time = models.IntegerField(help_text="Time required for rest in minutes")

    def __str__(self):
        return f"Bunker Load for {self.zames} in {self.bunker}"

class BlockProduction(models.Model):
    STATUS_CHOICES = (
        ('COOLING', 'Sovutilmoqda'),
        ('READY', 'Tayyor'),
        ('DEFECT', 'Brak'),
        ('RESERVED', 'Band qilingan'),
        ('SOLD', 'Sotilgan'),
    )

    production_batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='blocks', null=True, blank=True)
    zames = models.ForeignKey(Zames, on_delete=models.CASCADE, related_name='blocks')
    form_number = models.CharField(max_length=50)
    block_count = models.IntegerField()
    
    # Physical Parameters
    length = models.FloatField(default=1000, help_text="mm")
    width = models.FloatField(default=500, help_text="mm")
    height = models.FloatField(default=500, help_text="mm")
    density = models.FloatField(default=20, help_text="kg/m3")
    
    volume = models.DecimalField(max_digits=18, decimal_places=4, default=0, help_text="Total volume in m3")
    weight_per_block = models.DecimalField(max_digits=18, decimal_places=3, default=0, help_text="kg")
    
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='COOLING')
    warehouse = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True)
    
    operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='produced_blocks')
    shift = models.CharField(max_length=20, choices=(('DAY', 'Kunlik'), ('NIGHT', 'Tungi')), default='DAY')
    date = models.DateField(auto_now_add=True)

    def save(self, *args, **kwargs):
        from decimal import Decimal
        if not self.volume:
            self.volume = (Decimal(str(self.length)) * Decimal(str(self.width)) * Decimal(str(self.height)) / Decimal('1e9')) * Decimal(str(self.block_count))
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Lot {self.id} | {self.block_count} blocks | {self.density} kg/m3"

class FinishedBlock(models.Model):
    CLASSIFICATION_CHOICES = (
        ('A_CLASS', 'A-Class (Premium)'),
        ('B_CLASS', 'B-Class (Standard)'),
        ('C_CLASS', 'C-Class (Economic)'),
        ('REJECT', 'Reject (Brak)'),
    )
    
    STATUS_CHOICES = (
        ('COOLING', 'Sovutilmoqda'),
        ('QC_PENDING', 'Sifat nazoratida'),
        ('READY', 'Sotuvga tayyor'),
        ('RESERVED', 'Band qilingan'),
        ('SOLD', 'Sotilgan'),
        ('RECYCLE', 'Qayta ishlashga'),
    )

    block_id = models.CharField(max_length=50, unique=True) # BLK-2026-000001
    lot = models.ForeignKey(BlockProduction, on_delete=models.CASCADE, related_name='individual_blocks')
    
    # Passport Data
    classification = models.CharField(max_length=20, choices=CLASSIFICATION_CHOICES, default='B_CLASS')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='COOLING')
    
    # Physicals
    actual_weight = models.FloatField(null=True, blank=True)
    actual_density = models.FloatField(null=True, blank=True)
    moisture = models.FloatField(null=True, blank=True, help_text="%")
    
    # Precise dimensions (can deviate from lot standard)
    length = models.FloatField(null=True, blank=True, help_text="mm")
    width = models.FloatField(null=True, blank=True, help_text="mm")
    height = models.FloatField(null=True, blank=True, help_text="mm")
    
    visual_defects = models.TextField(blank=True, help_text="Visual defects description or tags")
    
    # Location
    warehouse = models.ForeignKey('warehouse_v2.Warehouse', on_delete=models.SET_NULL, null=True, blank=True)
    zone = models.CharField(max_length=50, blank=True)
    rack = models.CharField(max_length=50, blank=True)
    
    qr_code_data = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.block_id} ({self.classification})"

class BlockTimeline(models.Model):
    block = models.ForeignKey(FinishedBlock, on_delete=models.CASCADE, related_name='timeline')
    status = models.CharField(max_length=50)
    notes = models.TextField(blank=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.block.block_id} -> {self.status} at {self.timestamp}"

class DryingProcess(models.Model):
    block_production = models.ForeignKey(BlockProduction, on_delete=models.CASCADE, related_name='drying_processes')
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Drying for {self.block_production}"
class ProductionOrder(StateMachineMixin, models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('PLANNED', 'Rejalashtirilgan'),
        ('IN_PROGRESS', 'Jarayonda'),
        ('QC_PENDING', 'Sifat Nazorati'),
        ('REPAIR', 'Brak / Qayta ishlov'),
        ('DELAYED', 'Kechikayotgan'),
        ('COMPLETED', 'Tugallangan'),
        ('CANCELLED', 'Bekor qilingan'),
        ('FAILED', 'Xatolik / To‘xtagan'),
    )

    STATUS_TRANSITIONS = {
        'PENDING': ['PLANNED', 'IN_PROGRESS', 'CANCELLED'],
        'PLANNED': ['IN_PROGRESS', 'CANCELLED'],
        'IN_PROGRESS': ['QC_PENDING', 'COMPLETED', 'DELAYED', 'FAILED', 'CANCELLED'],
        'QC_PENDING': ['COMPLETED', 'REPAIR', 'FAILED'],
        'REPAIR': ['IN_PROGRESS', 'QC_PENDING', 'FAILED'],
        'DELAYED': ['IN_PROGRESS', 'COMPLETED', 'CANCELLED'],
        'COMPLETED': [],
        'CANCELLED': ['PENDING'],
        'FAILED': ['IN_PROGRESS', 'REPAIR', 'CANCELLED'],
    }

    order_number = models.CharField(max_length=50, unique=True)
    product = models.ForeignKey('warehouse_v2.Material', on_delete=models.SET_NULL, null=True)
    quantity = models.IntegerField(help_text="Volume in blocks or cubic meters")
    
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')
    progress = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Total completion percentage")
    priority = models.CharField(max_length=20, choices=(
        ('URGENT', 'Shoshilinch'),
        ('HIGH', 'Yuqori'),
        ('MEDIUM', 'O‘rtacha'),
        ('LOW', 'Past'),
    ), default='MEDIUM')
    
    start_date = models.DateTimeField(null=True, blank=True)
    deadline = models.DateTimeField(null=True, blank=True)
    
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='responsible_orders')
    source_order = models.CharField(max_length=100, blank=True, help_text="Link to MTO order or 'STOCK'")
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Order {self.order_number} ({self.status})"

class ProductionOrderStage(StateMachineMixin, models.Model):
    STAGE_TYPES = (
        ('ZAMES', 'Zames (Mixing)'),
        ('DRYING', 'Quritish'),
        ('BUNKER', 'Bunker (Resting)'),
        ('FORMOVKA', 'Formovka (Molding)'),
        ('BLOK', 'Blok (Cutting/Sizing)'),
        ('CNC', 'CNC (Cutting)'),
        ('DEKOR', 'Dekor (Finishing)'),
    )
    
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('ACTIVE', 'Aktiv'),
        ('DONE', 'Tugallangan'),
        ('PAUSED', 'To‘xtatilgan'),
        ('FAILED', 'Xatolik / To‘xtagan'),
    )

    STATUS_TRANSITIONS = {
        'PENDING': ['ACTIVE', 'FAILED'],
        'ACTIVE': ['DONE', 'PAUSED', 'FAILED'],
        'PAUSED': ['ACTIVE', 'FAILED'],
        'DONE': [],
        'FAILED': ['PENDING', 'ACTIVE'],
    }

    order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='stages')
    stage_type = models.CharField(max_length=50, choices=STAGE_TYPES)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='PENDING')
    
    sequence = models.IntegerField(default=0, help_text="Order of this stage in the pipeline")
    
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    responsible = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='assigned_stages')
    current_operator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name='active_worker_stages')
    
    # Execution metrics
    actual_quantity = models.FloatField(default=0)
    waste_amount = models.FloatField(default=0)
    
    # Optional link to concrete entity if applicable (e.g. Zames instance)
    related_id = models.IntegerField(null=True, blank=True, help_text="ID of the related entity like Zames object")
    
    # MES tracking
    shift = models.CharField(max_length=20, choices=(('DAY', 'Kunlik'), ('NIGHT', 'Tungi')), default='DAY')
    machine_status = models.CharField(max_length=20, choices=(
        ('ACTIVE', 'Aktiv'),
        ('MAINTENANCE', 'Texnik xizmat'),
        ('OFFLINE', 'O\'f-line'),
    ), default='ACTIVE')
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.order.order_number} - {self.get_stage_type_display()} ({self.status})"

class ProductionPlan(models.Model):
    STATUS_CHOICES = (
        ('DRAFT', 'Qoralama'),
        ('ACTIVE', 'Aktiv'),
        ('COMPLETED', 'Tugallandi'),
    )
    date = models.DateField()
    shift = models.CharField(max_length=20, choices=(('DAY', 'Kunlik'), ('NIGHT', 'Tungi')), default='DAY')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    
    orders = models.ManyToManyField(ProductionOrder, related_name='plans')
    target_volume = models.FloatField(default=0)
    actual_volume = models.FloatField(default=0)
    
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Plan for {self.date} ({self.shift})"

class QualityCheck(models.Model):
    STATUS_CHOICES = (
        ('PASSED', 'Tasdiqlandi'),
        ('FAILED', 'Rad etildi (Brak)'),
        ('PENDING', 'Kutilmoqda'),
    )
    
    order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='quality_checks')
    stage = models.ForeignKey(ProductionOrderStage, on_delete=models.SET_NULL, null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    notes = models.TextField(blank=True)
    waste_weight = models.FloatField(default=0, help_text="kg")
    
    inspector = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Extended QC
    failure_reason = models.CharField(max_length=100, blank=True, help_text="Density error, Size error, etc.")
    is_recycleable = models.BooleanField(default=True)
    photo = models.ImageField(upload_to='qc_photos/', null=True, blank=True)

    def __str__(self):
        return f"QC for {self.order.order_number}: {self.status}"

class StageActionLog(models.Model):
    ACTION_CHOICES = (
        ('START', 'Boshlash'),
        ('FINISH', 'Yakunlash'),
        ('FAIL', 'Xatolik'),
        ('PAUSE', 'To‘xtatish'),
        ('RESUME', 'Davom ettirish'),
        ('RESET', 'Qayta tiklash'),
    )
    
    order = models.ForeignKey(ProductionOrder, on_delete=models.CASCADE, related_name='stage_logs')
    stage = models.ForeignKey(ProductionOrderStage, on_delete=models.CASCADE, related_name='action_logs')
    stage_type = models.CharField(max_length=50) # Redundant for easier querying
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.order.order_number} - {self.stage_type} - {self.action} by {self.user}"

# ═══════════════════════════════════════════════════
# PHASE 4: COST ENGINE (ENTERPRISE PRODUCT COSTING)
# ═══════════════════════════════════════════════════

class EnergyUsage(models.Model):
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='energy_usages')
    type = models.CharField(max_length=20, choices=(('GAS', 'Gaz'), ('ELECTRICITY', 'Elektr')))
    quantity = models.FloatField(help_text="m3 or kWh")
    price_per_unit = models.DecimalField(max_digits=18, decimal_places=2, help_text="Tarif narxi")
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    is_auto_calculated = models.BooleanField(default=False)
    
    def save(self, *args, **kwargs):
        self.total_cost = float(self.quantity) * float(self.price_per_unit)
        super().save(*args, **kwargs)

class LaborCost(models.Model):
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='labor_costs')
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    hours = models.FloatField(help_text="Ishlangan soat yoki norma")
    rate_per_hour = models.DecimalField(max_digits=18, decimal_places=2, help_text="Soatbay yoki ishlab chiqarilgan m3/stk uchun stavka")
    total_cost = models.DecimalField(max_digits=18, decimal_places=2, default=0)
    
    def save(self, *args, **kwargs):
        self.total_cost = float(self.hours) * float(self.rate_per_hour)
        super().save(*args, **kwargs)

class OverheadCost(models.Model):
    batch = models.ForeignKey(ProductionBatch, on_delete=models.CASCADE, related_name='overhead_costs')
    cost_type = models.CharField(max_length=50, help_text="Masalan: Ijara, Amortizatsiya, Soliq qismi")
    amount = models.DecimalField(max_digits=18, decimal_places=2, default=0)
