from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import FinishingJob
from .serializers import FinishingJobSerializer
from .services import start_finishing_job, advance_finishing_stage, pause_finishing_job, resume_finishing_job, finish_finishing_job
from django.utils import timezone
from accounts.permissions import IsFinishingOperator, get_user_role_name

class FinishingJobViewSet(viewsets.ModelViewSet):
    serializer_class = FinishingJobSerializer
    permission_classes = [IsFinishingOperator]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return FinishingJob.objects.none()
        user = self.request.user
        # Admins/Supervisors see all, others see only assigned
        if user.is_superuser or user.is_staff or get_user_role_name(user) in ['Bosh Admin', 'Admin', 'Ishlab chiqarish ustasi', 'PRODUCTION_MASTER', 'SUPERADMIN', 'ADMIN']:
            return FinishingJob.objects.all().order_by('-created_at')
        return FinishingJob.objects.filter(operator=user).order_by('-created_at')

    def perform_create(self, serializer):
        job_number = f"ARM-{timezone.now().strftime('%y%m%d%H%M%S')}"
        serializer.save(job_number=job_number)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        job = start_finishing_job(pk, operator=request.user)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def advance(self, request, pk=None):
        job = advance_finishing_stage(pk, operator=request.user)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def pause(self, request, pk=None):
        job = pause_finishing_job(pk)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def resume(self, request, pk=None):
        job = resume_finishing_job(pk, operator=request.user)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        finished_qty = request.data.get('finished_qty')
        waste_qty = request.data.get('waste_qty', 0)
        
        if finished_qty is None:
             return Response({"error": "finished_qty is required"}, status=400)
             
        job = finish_finishing_job(
            pk, 
            finished_qty=int(finished_qty), 
            waste_qty=int(waste_qty), 
            operator=request.user
        )
        return Response(self.get_serializer(job).data)
