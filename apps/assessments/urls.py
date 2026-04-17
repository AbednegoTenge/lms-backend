from django.urls import path

from apps.assessments.views import QuizAttemptViewSet, QuizViewSet, ResourceViewSet

resource_list = ResourceViewSet.as_view({'get': 'list', 'post': 'create'})
resource_detail = ResourceViewSet.as_view({'delete': 'destroy'})

quiz_list = QuizViewSet.as_view({'get': 'list', 'post': 'create'})
quiz_detail = QuizViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'})
quiz_publish = QuizViewSet.as_view({'post': 'publish'})
quiz_attempts = QuizViewSet.as_view({'post': 'start_attempt'})
quiz_submissions = QuizViewSet.as_view({'get': 'submissions'})

attempt_submit = QuizAttemptViewSet.as_view({'post': 'submit'})

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
    # Quiz endpoints
    path('quizzes/', quiz_list, name='quiz-list'),
    path('quizzes/<uuid:pk>/', quiz_detail, name='quiz-detail'),
    path('quizzes/<uuid:pk>/publish/', quiz_publish, name='quiz-publish'),
    path('quizzes/<uuid:pk>/attempts/', quiz_attempts, name='quiz-attempts'),
    path('quizzes/<uuid:pk>/submissions/', quiz_submissions, name='quiz-submissions'),
    # Attempt submit
    path('quiz-attempts/<uuid:pk>/submit/', attempt_submit, name='attempt-submit'),
]
