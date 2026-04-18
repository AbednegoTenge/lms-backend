from django.urls import path

from apps.fees.views import FeeStructureViewSet, StudentFeeViewSet

fee_structure_list = FeeStructureViewSet.as_view({'get': 'list', 'post': 'create'})
fee_structure_detail = FeeStructureViewSet.as_view({'patch': 'partial_update', 'delete': 'destroy'})

student_fee_list = StudentFeeViewSet.as_view({'get': 'list'})
student_fee_detail = StudentFeeViewSet.as_view({'get': 'retrieve'})
student_fee_payments = StudentFeeViewSet.as_view({'post': 'payments'})
student_fee_reminder = StudentFeeViewSet.as_view({'post': 'send_reminder'})

urlpatterns = [
    path('fee-structures/', fee_structure_list, name='fee-structure-list'),
    path('fee-structures/<uuid:pk>/', fee_structure_detail, name='fee-structure-detail'),

    path('student-fees/', student_fee_list, name='student-fee-list'),
    path('student-fees/send-reminder/', student_fee_reminder, name='student-fee-reminder'),
    path('student-fees/<uuid:pk>/', student_fee_detail, name='student-fee-detail'),
    path('student-fees/<uuid:pk>/payments/', student_fee_payments, name='student-fee-payments'),
]
