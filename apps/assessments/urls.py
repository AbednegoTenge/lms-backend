from django.urls import path

from apps.assessments.views import (
    AssignmentSubmissionViewSet,
    CourseAssignmentViewSet,
    QuizAttemptViewSet,
    QuizViewSet,
    ResourceViewSet,
    TeacherEvaluationViewSet,
)

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

    # Course assignments
    path(
        'course-assignments/',
        CourseAssignmentViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='course-assignment-list',
    ),
    path(
        'course-assignments/<uuid:pk>/',
        CourseAssignmentViewSet.as_view({'get': 'retrieve', 'patch': 'partial_update'}),
        name='course-assignment-detail',
    ),
    path(
        'course-assignments/<uuid:pk>/publish/',
        CourseAssignmentViewSet.as_view({'post': 'publish'}),
        name='course-assignment-publish',
    ),
    path(
        'course-assignments/<uuid:pk>/submit/',
        CourseAssignmentViewSet.as_view({'post': 'submit'}),
        name='course-assignment-submit',
    ),
    path(
        'course-assignments/<uuid:pk>/submissions/',
        CourseAssignmentViewSet.as_view({'get': 'submissions'}),
        name='course-assignment-submissions',
    ),

    # Submission grading
    path(
        'assignment-submissions/<uuid:pk>/grade/',
        AssignmentSubmissionViewSet.as_view({'patch': 'grade'}),
        name='assignment-submission-grade',
    ),

    # Teacher evaluations
    path(
        'evaluations/',
        TeacherEvaluationViewSet.as_view({'get': 'list', 'post': 'create'}),
        name='evaluation-list',
    ),
]
