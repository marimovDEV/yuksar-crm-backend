from django.contrib import admin
from .models import AuditLog, Notification, UserGuideSection, UserGuideContent, SupportTicket, VideoTutorial

@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('timestamp', 'module', 'action', 'user', 'status')
    list_filter = ('module', 'action', 'status')
    search_fields = ('description', 'user__username', 'model_name')
    readonly_fields = ('timestamp', 'old_value', 'new_value')

@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'type', 'is_read', 'created_at')
    list_filter = ('type', 'is_read')
    search_fields = ('title', 'message', 'user__username')

class UserGuideContentInline(admin.TabularInline):
    model = UserGuideContent
    extra = 1

@admin.register(UserGuideSection)
class UserGuideSectionAdmin(admin.ModelAdmin):
    list_display = ('title_uz', 'title_ru', 'order', 'icon', 'is_active')
    list_display_links = ('title_uz',)
    list_editable = ('order', 'is_active')
    inlines = [UserGuideContentInline]

@admin.register(UserGuideContent)
class UserGuideContentAdmin(admin.ModelAdmin):
    list_display = ('title_uz', 'section', 'role', 'order', 'is_active')
    list_display_links = ('title_uz',)
    list_filter = ('section', 'role', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('title_uz', 'title_ru', 'body_uz', 'body_ru')

@admin.register(SupportTicket)
class SupportTicketAdmin(admin.ModelAdmin):
    list_display = ('subject', 'user', 'status', 'priority', 'created_at')
    list_filter = ('status', 'priority')
    search_fields = ('subject', 'message', 'user__username')

@admin.register(VideoTutorial)
class VideoTutorialAdmin(admin.ModelAdmin):
    list_display = ('title_uz', 'order', 'is_active')
    list_editable = ('order', 'is_active')
    search_fields = ('title_uz', 'title_ru')
