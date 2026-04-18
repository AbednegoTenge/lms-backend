from django.urls import path

from apps.announcements.views import AnnouncementViewSet

announcement_list = AnnouncementViewSet.as_view({'get': 'list', 'post': 'create'})
announcement_detail = AnnouncementViewSet.as_view({
    'get': 'retrieve', 'patch': 'partial_update', 'delete': 'destroy'
})
announcement_publish = AnnouncementViewSet.as_view({'post': 'publish'})
announcement_read = AnnouncementViewSet.as_view({'post': 'read'})

urlpatterns = [
    path('announcements/', announcement_list, name='announcement-list'),
    path('announcements/<uuid:pk>/', announcement_detail, name='announcement-detail'),
    path('announcements/<uuid:pk>/publish/', announcement_publish, name='announcement-publish'),
    path('announcements/<uuid:pk>/read/', announcement_read, name='announcement-read'),
]
