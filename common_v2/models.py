from django.db import models
from django.conf import settings

class AuditLog(models.Model):
    ACTION_CHOICES = (
        ('CREATE', 'Yaratish'),
        ('UPDATE', 'Tahrirlash'),
        ('DELETE', 'O\'chirish'),
        ('LOGIN', 'Kirish'),
        ('LOGOUT', 'Chiqish'),
        ('TRANSFER', 'O\'tkazma'),
        ('ERROR', 'Xatolik'),
    )

    STATUS_CHOICES = (
        ('SUCCESS', 'Muvaffaqiyatli'),
        ('ERROR', 'Xatolik'),
        ('WARNING', 'Ogohlantirish'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    module = models.CharField(max_length=50) 
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    object_id = models.CharField(max_length=100, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='SUCCESS')

    # Enterprise Audit Fields (NEW)
    old_value = models.JSONField(null=True, blank=True, help_text="O'zgarishdan oldingi qiymat")
    new_value = models.JSONField(null=True, blank=True, help_text="O'zgarishdan keyingi qiymat")
    model_name = models.CharField(max_length=100, null=True, blank=True, help_text="Model nomi (masalan: Invoice)")

    def __str__(self):
        return f"[{self.module}] {self.user} - {self.action}: {self.description[:50]}"

    class Meta:
        ordering = ['-timestamp']

class Notification(models.Model):
    TYPE_CHOICES = (
        ('INFO', 'Ma\'lumot'),
        ('WARNING', 'Ogohlantirish'),
        ('ERROR', 'Xatolik'),
        ('SUCCESS', 'Muvaffaqiyatli'),
    )

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=255)
    message = models.TextField()
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='INFO')
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    link = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.user} - {self.title}"

    class Meta:
        ordering = ['-created_at']

class UserGuideSection(models.Model):
    """
    Documentation sections (e.g. Warehouse, Production, Finance)
    """
    title_uz = models.CharField(max_length=255)
    title_ru = models.CharField(max_length=255)
    icon = models.CharField(max_length=50, help_text="Lucide icon name (e.g. Layout, Database)")
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "User Guide Section"
        verbose_name_plural = "User Guide Sections"

    def __str__(self):
        return self.title_uz

class UserGuideContent(models.Model):
    """
    Detailed content blocks within a section, can be role-specific.
    """
    section = models.ForeignKey(UserGuideSection, on_delete=models.CASCADE, related_name='contents')
    role = models.ForeignKey('accounts.ERPRole', on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional: only show to this role")
    
    title_uz = models.CharField(max_length=255)
    title_ru = models.CharField(max_length=255)
    
    body_uz = models.TextField()
    body_ru = models.TextField()
    
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', 'created_at']
        verbose_name = "User Guide Content"
        verbose_name_plural = "User Guide Contents"

    def __str__(self):
        return f"[{self.section.title_uz}] {self.title_uz}"

class SupportTicket(models.Model):
    """
    User support requests / feedback.
    """
    STATUS_CHOICES = (
        ('OPEN', 'Ochiq'),
        ('IN_PROGRESS', 'Jarayonda'),
        ('RESOLVED', 'Hal qilindi'),
        ('CLOSED', 'Yopildi'),
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='support_tickets')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    priority = models.CharField(max_length=20, choices=(('LOW', 'Past'), ('MEDIUM', 'O\'rta'), ('HIGH', 'Yuqori')), default='MEDIUM')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.subject} ({self.status})"

class VideoTutorial(models.Model):
    """
    Video lessons for the User Guide.
    """
    title_uz = models.CharField(max_length=255)
    title_ru = models.CharField(max_length=255)
    video_url = models.URLField(help_text="YouTube or internal video link")
    thumbnail = models.FileField(upload_to='tutorials/thumbnails/', null=True, blank=True)
    description_uz = models.TextField(blank=True)
    description_ru = models.TextField(blank=True)
    order = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'title_uz']

    def __str__(self):
        return self.title_uz
