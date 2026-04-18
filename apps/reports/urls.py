from django.urls import path

from apps.reports.views import ReportViewSet

academic_performance = ReportViewSet.as_view({'get': 'academic_performance'})
fee_collection = ReportViewSet.as_view({'get': 'fee_collection'})
teacher_evaluations = ReportViewSet.as_view({'get': 'teacher_evaluations'})
export_view = ReportViewSet.as_view({'post': 'export'})
export_status_view = ReportViewSet.as_view({'get': 'export_status'})

urlpatterns = [
    path('reports/academic-performance/', academic_performance, name='report-academic'),
    path('reports/fee-collection/', fee_collection, name='report-fee-collection'),
    path('reports/teacher-evaluations/', teacher_evaluations, name='report-teacher-evaluations'),
    path('reports/export/', export_view, name='report-export'),
    path('reports/export/<uuid:pk>/', export_status_view, name='report-export-status'),
]
