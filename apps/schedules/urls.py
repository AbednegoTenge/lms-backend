from django.urls import path

from apps.schedules.views import ClassTimetableViewSet, ExamScheduleViewSet, HolidayViewSet

timetable_list = ClassTimetableViewSet.as_view({'get': 'list', 'post': 'create'})
timetable_detail = ClassTimetableViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})

exam_list = ExamScheduleViewSet.as_view({'get': 'list', 'post': 'create'})
exam_detail = ExamScheduleViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})

holiday_list = HolidayViewSet.as_view({'get': 'list', 'post': 'create'})
holiday_detail = HolidayViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'})

urlpatterns = [
    path('timetables/', timetable_list, name='timetable-list'),
    path('timetables/<uuid:pk>/', timetable_detail, name='timetable-detail'),
    path('exam-schedules/', exam_list, name='exam-schedule-list'),
    path('exam-schedules/<uuid:pk>/', exam_detail, name='exam-schedule-detail'),
    path('holidays/', holiday_list, name='holiday-list'),
    path('holidays/<uuid:pk>/', holiday_detail, name='holiday-detail'),
]
