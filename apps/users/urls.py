from django.urls import path

from apps.users.views import (
    FirstLoginResetView,
    LoginView,
    LogoutView,
    TeacherListView,
    TokenRefreshWrappedView,
)

urlpatterns = [
    path('login/', LoginView.as_view(), name='auth-login'),
    path('refresh/', TokenRefreshWrappedView.as_view(), name='auth-refresh'),
    path('logout/', LogoutView.as_view(), name='auth-logout'),
    path('first-login-reset/', FirstLoginResetView.as_view(), name='auth-first-login-reset'),
    path('teachers/', TeacherListView.as_view(), name='teacher-list'),
]
