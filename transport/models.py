from django.db import models
from django.conf import settings
from decimal import Decimal

class Driver(models.Model):
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50)
    passport_info = models.CharField(max_length=100, blank=True)
    vehicle_number = models.CharField(max_length=50)
    vehicle_type = models.CharField(max_length=100, blank=True)
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.full_name} ({self.vehicle_number})"

class TransportContract(models.Model):
    PAYMENT_TYPE_CHOICES = (
        ('PER_KM', 'Kilometr bo‘yicha (Per KM)'),
        ('PER_TRIP', 'Reys bo‘yicha (Fixed per Trip)'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Aktiv'),
        ('EXPIRED', 'Muddati o‘tgan'),
        ('CANCELLED', 'Bekor qilingan'),
    )
    
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='contracts')
    contract_number = models.CharField(max_length=50, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()
    
    price_per_km = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price_per_trip = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_type = models.CharField(max_length=10, choices=PAYMENT_TYPE_CHOICES, default='PER_KM')
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='ACTIVE')
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Contract {self.contract_number} - {self.driver.full_name}"

class Waybill(models.Model):
    PURPOSE_CHOICES = (
        ('CLIENT', 'Mijozga yetkazish (Client)'),
        ('PROJECT', 'Ichki loyiha (Project)'),
        ('TRANSFER', 'Omborlararo o‘tkazma (Transfer)'),
    )
    STATUS_CHOICES = (
        ('DRAFT', 'Qoralama'),
        ('CONFIRMED', 'Tasdiqlangan'),
        ('COMPLETED', 'Yakunlandi'),
        ('CANCELLED', 'Bekor qilingan'),
    )
    
    waybill_number = models.CharField(max_length=50, unique=True)
    driver = models.ForeignKey(Driver, on_delete=models.PROTECT, related_name='waybills')
    date = models.DateField(default=models.functions.Now())
    
    from_location = models.CharField(max_length=255, default='Asosiy Zavod')
    to_location = models.CharField(max_length=255)
    purpose = models.CharField(max_length=10, choices=PURPOSE_CHOICES, default='CLIENT')
    
    distance_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    fuel_given = models.DecimalField(max_digits=10, decimal_places=2, default=0, help_text="Berilgan yoqilg'i (litr)")
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    dispatcher = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name='dispatched_waybills')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Waybill {self.waybill_number} | {self.driver.full_name}"

class Trip(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'Kutilmoqda'),
        ('EN_ROUTE', 'Yo‘lda'),
        ('DELIVERED', 'Yetkazildi'),
        ('COMPLETED', 'Yakunlandi'),
        ('CANCELLED', 'Bekor qilingan'),
    )
    
    waybill = models.OneToOneField(Waybill, on_delete=models.CASCADE, related_name='trip')
    related_delivery = models.ForeignKey('logistics.Delivery', on_delete=models.SET_NULL, null=True, blank=True, related_name='trips')
    
    start_time = models.DateTimeField(null=True, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    actual_distance = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Trip for {self.waybill.waybill_number}"

class DriverPayment(models.Model):
    STATUS_CHOICES = (
        ('PENDING', 'To‘lov kutilmoqda'),
        ('PAID', 'To‘landi'),
    )
    
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='payments')
    trip = models.OneToOneField(Trip, on_delete=models.CASCADE, related_name='payment')
    
    calculated_km = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='PENDING')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.id} | {self.driver.full_name} | {self.amount}"

class Vehicle(models.Model):
    TYPE_CHOICES = (
        ('TRUCK', 'Yuk mashinasi'),
        ('VAN', 'Mikroavtobus'),
        ('CAR', 'Avtomobil'),
        ('LOADER', 'Yuk ko\'taruvchi'),
    )
    STATUS_CHOICES = (
        ('ACTIVE', 'Faol'),
        ('MAINTENANCE', 'Ta\'mirda'),
        ('INACTIVE', 'Nofaol'),
    )

    plate = models.CharField(max_length=20, unique=True, verbose_name='Davlat raqami')
    vehicle_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='TRUCK')
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    year = models.IntegerField(null=True, blank=True)
    capacity_kg = models.DecimalField(max_digits=10, decimal_places=2, default=0, verbose_name='Yuk ko\'tarish qobiliyati (kg)')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='ACTIVE')
    driver = models.ForeignKey(Driver, on_delete=models.SET_NULL, null=True, blank=True, related_name='vehicles')
    mileage_km = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.plate} ({self.vehicle_type})"

    class Meta:
        ordering = ['-created_at']


class FuelLog(models.Model):
    driver = models.ForeignKey(Driver, on_delete=models.CASCADE, related_name='fuel_logs')
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='fuel_logs')
    
    fuel_given = models.DecimalField(max_digits=10, decimal_places=2)
    fuel_used = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    norm = models.DecimalField(max_digits=10, decimal_places=2, help_text="Litr per 100km or total norm")
    
    difference = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"Fuel Log | {self.driver.full_name} | Trip {self.trip.id}"
