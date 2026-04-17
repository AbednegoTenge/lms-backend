import datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.academics.models import AcademicYear
from tests.factories import AcademicYearFactory, UserFactory


def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


BASE_URL = '/api/v1/academic-years/'


@pytest.mark.django_db
class TestAcademicYearPermissions:
    def test_unauthenticated_cannot_list(self, api_client):
        res = api_client.get(BASE_URL)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_student_can_list(self, student_user):
        client = auth_client(student_user)
        res = client.get(BASE_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_teacher_can_list(self, teacher_user):
        client = auth_client(teacher_user)
        res = client.get(BASE_URL)
        assert res.status_code == status.HTTP_200_OK

    def test_student_cannot_create(self, student_user):
        client = auth_client(student_user)
        res = client.post(BASE_URL, {
            'name': '2030/2031',
            'start_date': '2030-09-01',
            'end_date': '2031-07-31',
            'is_current': False,
        }, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_create(self, teacher_user):
        client = auth_client(teacher_user)
        res = client.post(BASE_URL, {
            'name': '2030/2031',
            'start_date': '2030-09-01',
            'end_date': '2031-07-31',
            'is_current': False,
        }, format='json')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_create(self, admin_user):
        client = auth_client(admin_user)
        res = client.post(BASE_URL, {
            'name': '2030/2031',
            'start_date': '2030-09-01',
            'end_date': '2031-07-31',
            'is_current': False,
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data['success'] is True

    def test_admin_can_update(self, admin_user, db):
        yr = AcademicYearFactory()
        client = auth_client(admin_user)
        res = client.patch(f'{BASE_URL}{yr.pk}/', {'name': 'Updated/Year'}, format='json')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['data']['name'] == 'Updated/Year'

    def test_student_cannot_delete(self, student_user, db):
        yr = AcademicYearFactory()
        client = auth_client(student_user)
        res = client.delete(f'{BASE_URL}{yr.pk}/')
        assert res.status_code == status.HTTP_403_FORBIDDEN

    def test_admin_can_delete(self, admin_user, db):
        yr = AcademicYearFactory()
        client = auth_client(admin_user)
        res = client.delete(f'{BASE_URL}{yr.pk}/')
        assert res.status_code == status.HTTP_204_NO_CONTENT
        assert not AcademicYear.objects.filter(pk=yr.pk).exists()


@pytest.mark.django_db
class TestAcademicYearCRUD:
    def test_create_returns_correct_fields(self, admin_user):
        client = auth_client(admin_user)
        res = client.post(BASE_URL, {
            'name': '2025/2026',
            'start_date': '2025-09-01',
            'end_date': '2026-07-31',
            'is_current': True,
        }, format='json')
        assert res.status_code == status.HTTP_201_CREATED
        data = res.data['data']
        assert data['name'] == '2025/2026'
        assert data['is_current'] is True

    def test_only_one_is_current_enforced_via_api(self, admin_user, db):
        client = auth_client(admin_user)
        client.post(BASE_URL, {
            'name': '2025/2026', 'start_date': '2025-09-01',
            'end_date': '2026-07-31', 'is_current': True,
        }, format='json')
        client.post(BASE_URL, {
            'name': '2026/2027', 'start_date': '2026-09-01',
            'end_date': '2027-07-31', 'is_current': True,
        }, format='json')
        assert AcademicYear.objects.filter(is_current=True).count() == 1

    def test_start_date_before_end_date_validated(self, admin_user):
        client = auth_client(admin_user)
        res = client.post(BASE_URL, {
            'name': 'Bad/Year',
            'start_date': '2025-07-31',
            'end_date': '2025-01-01',
            'is_current': False,
        }, format='json')
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_filter_by_is_current(self, admin_user, db):
        AcademicYearFactory(is_current=True)
        AcademicYearFactory(is_current=False)
        client = auth_client(admin_user)
        res = client.get(f'{BASE_URL}?is_current=true')
        assert res.status_code == status.HTTP_200_OK
        results = res.data['data']
        assert all(r['is_current'] for r in results)

    def test_retrieve_returns_envelope(self, admin_user, db):
        yr = AcademicYearFactory()
        client = auth_client(admin_user)
        res = client.get(f'{BASE_URL}{yr.pk}/')
        assert res.status_code == status.HTTP_200_OK
        assert res.data['success'] is True
        assert res.data['data']['id'] == str(yr.pk)
