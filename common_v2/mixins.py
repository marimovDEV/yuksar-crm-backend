from django.db import models
from rest_framework.exceptions import ValidationError, MethodNotAllowed
from common_v2.services import log_action

class NoDeleteMixin:
    """
    Mixin to prevent record deletion in DRF views.
    Ensures that important enterprise documents can only be cancelled, not deleted.
    """
    def destroy(self, request, *args, **kwargs):
        raise MethodNotAllowed(request.method, detail="Hujjatni o'chirib bo'lmaydi. Faqat 'Bekor qilish' mumkin.")
    
    def perform_destroy(self, instance):
        raise MethodNotAllowed('DELETE', detail="Hujjatni o'chirib bo'lmaydi. Faqat 'Bekor qilish' mumkin.")

class StateMachineMixin:
    """
    Mixin to enforce strict state transitions.
    Models using this must define a 'STATUS_TRANSITIONS' dict.
    Example:
    STATUS_TRANSITIONS = {
        'PENDING': ['IN_PROGRESS', 'CANCELLED'],
        'IN_PROGRESS': ['DONE', 'FAILED'],
    }
    """
    
    def transition_to(self, new_status, user=None, reason=None, force=False):
        old_status = getattr(self, 'status', None)
        if not old_status:
            raise ValidationError("Modelda status maydoni topilmadi.")
            
        allowed_transitions = getattr(self, 'STATUS_TRANSITIONS', {}).get(old_status, [])
        
        if not force and new_status not in allowed_transitions and old_status != new_status:
            raise ValidationError(
                f"Noto'g'ri status o'tishi: {old_status} -> {new_status}. "
                f"Ruxsat berilgan: {', '.join(allowed_transitions)}"
            )
            
        self.status = new_status
        self.save()
        
        # Automatic audit log for status change
        log_action(
            user=user,
            action='UPDATE',
            module=self._meta.app_label.upper(),
            description=f"Status o'zgartirildi: {self._meta.model_name} {getattr(self, 'id', '')}",
            object_id=getattr(self, 'id', None),
            old_value={'status': old_status},
            new_value={'status': new_status}
        )
        return True

class LoggedModelMixin(models.Model):
    """
    Mixin to automatically capture field changes on save.
    """
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk:
            # Fetch the current state from DB for comparison
            cls = self.__class__
            old_instance = cls.objects.get(pk=self.pk)
            # Add field-level comparison logic here if needed
            # For now, it's used as a marker for high-integrity models
        super().save(*args, **kwargs)
