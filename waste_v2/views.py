from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import WasteTask, WasteCategory
from .serializers import WasteTaskSerializer, WasteCategorySerializer
from .services import start_processing_waste, finish_processing_waste, accept_waste, get_waste_stats
from accounts.permissions import IsWasteOperator, IsProductionRelated, IsAdminOrDirector

class WasteCategoryViewSet(viewsets.ModelViewSet):
    queryset = WasteCategory.objects.all()
    serializer_class = WasteCategorySerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [IsWasteOperator() | IsProductionRelated() | IsAdminOrDirector()]
        return [IsWasteOperator()]

class WasteTaskViewSet(viewsets.ModelViewSet):
    queryset = WasteTask.objects.all().order_by('-created_at')
    serializer_class = WasteTaskSerializer
    permission_classes = [IsWasteOperator]

    def create(self, request, *args, **kwargs):
        """
        Manually override create to use service.
        """
        data = request.data
        task = accept_waste(
            source_department=data.get('source_department'),
            weight_kg=float(data.get('weight_kg')),
            category_id=int(data.get('category')),
            batch_number=data.get('batch_number'),
            operator=request.user
        )
        serializer = self.get_serializer(task)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        try:
            task = start_processing_waste(pk)
            return Response(WasteTaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'])
    def finish(self, request, pk=None):
        try:
            recycled = float(request.data.get('recycled_weight_kg', 0))
            loss = float(request.data.get('loss_weight_kg', 0))
            notes = request.data.get('notes')
            task = finish_processing_waste(pk, recycled, loss, notes)
            return Response(WasteTaskSerializer(task).data)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['get'])
    def stats(self, request):
        return Response(get_waste_stats())
