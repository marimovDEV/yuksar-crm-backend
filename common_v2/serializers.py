from rest_framework import serializers
from .models import AuditLog, Notification, UserGuideSection, UserGuideContent, SupportTicket, VideoTutorial

class AuditLogSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)

    class Meta:
        model = AuditLog
        fields = '__all__'

class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'

class UserGuideContentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserGuideContent
        fields = ['id', 'role', 'title_uz', 'title_ru', 'body_uz', 'body_ru', 'order']

class UserGuideSectionSerializer(serializers.ModelSerializer):
    contents = UserGuideContentSerializer(many=True, read_only=True)
    
    class Meta:
        model = UserGuideSection
        fields = ['id', 'title_uz', 'title_ru', 'icon', 'order', 'contents']

class SupportTicketSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source='user.full_name', read_only=True)
    
    class Meta:
        model = SupportTicket
        fields = '__all__'
        read_only_fields = ['user', 'status']

class VideoTutorialSerializer(serializers.ModelSerializer):
    class Meta:
        model = VideoTutorial
        fields = '__all__'
