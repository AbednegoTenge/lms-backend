import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from tests.factories.user_factory import UserFactory, RoleFactory, UserRoleFactory


@pytest.fixture(autouse=True)
def disable_throttling(settings):
    """Disable throttling and clear the cache (throttle state) between tests."""
    from django.core.cache import cache
    cache.clear()
    settings.REST_FRAMEWORK = {
        **settings.REST_FRAMEWORK,
        'DEFAULT_THROTTLE_CLASSES': [],
        'DEFAULT_THROTTLE_RATES': {},
    }
    # Patch view-level throttle classes to allow unlimited requests in tests
    from apps.users import views as user_views
    original = user_views.LoginView.throttle_classes
    user_views.LoginView.throttle_classes = []
    yield
    user_views.LoginView.throttle_classes = original


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def student_user(db):
    return UserFactory(role='STUDENT')


@pytest.fixture
def teacher_user(db):
    return UserFactory(role='TEACHER')


@pytest.fixture
def admin_user(db):
    return UserFactory(role='ADMIN')


@pytest.fixture
def it_support_user(db):
    return UserFactory(role='IT_SUPPORT')


@pytest.fixture
def auth_client(api_client, admin_user):
    """APIClient authenticated as an admin with a fresh JWT."""
    refresh = RefreshToken.for_user(admin_user)
    api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return api_client


def get_tokens_for_user(user):
    refresh = RefreshToken.for_user(user)
    return str(refresh.access_token), str(refresh)
