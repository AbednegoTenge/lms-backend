from django.urls import path

from apps.assessments.views import ResourceViewSet

resource_list = ResourceViewSet.as_view({'get': 'list', 'post': 'create'})
resource_detail = ResourceViewSet.as_view({'delete': 'destroy'})

urlpatterns = [
    path(
        'assignments/<uuid:assignment_pk>/resources/',
        resource_list,
        name='resource-list',
    ),
    path(
        'assignments/<uuid:assignment_pk>/resources/<uuid:pk>/',
        resource_detail,
        name='resource-detail',
    ),
]
