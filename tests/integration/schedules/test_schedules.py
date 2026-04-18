"""
Integration tests for Phase 8 — Schedules.

Covers:
  - ClassTimetable CRUD (admin write, all-auth read)
  - Timetable conflict: same room same time → 409
  - Timetable conflict: same teacher same time → 409
  - No conflict: same room different day → 201
  - ExamSchedule CRUD
  - Holiday CRUD
  - Permission matrix
"""
import datetime

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.schedules.models import ClassTimetable, ExamSchedule, Holiday
from tests.factories import (
    AcademicYearFactory,
    ClassTimetableFactory,
    CourseFactory,
    ExamScheduleFactory,
    HolidayFactory,
    LevelFactory,
    TermFactory,
    UserFactory,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
    return client


TIMETABLE_LIST = '/api/v1/timetables/'
EXAM_LIST = '/api/v1/exam-schedules/'
HOLIDAY_LIST = '/api/v1/holidays/'


def timetable_url(pk):
    return f'/api/v1/timetables/{pk}/'


def exam_url(pk):
    return f'/api/v1/exam-schedules/{pk}/'


def holiday_url(pk):
    return f'/api/v1/holidays/{pk}/'


def _timetable_payload(course, teacher, level, term, room='R1', day=0,
                        start='08:00', end='09:00'):
    return {
        'course': str(course.pk),
        'teacher': str(teacher.pk),
        'level': str(level.pk),
        'class_section': '1A',
        'term': str(term.pk),
        'day_of_week': day,
        'start_time': start,
        'end_time': end,
        'room': room,
    }


# ---------------------------------------------------------------------------
# ClassTimetable tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestClassTimetableCRUD:

    def test_admin_can_create_timetable(self):
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        course = CourseFactory()
        teacher = UserFactory(role='TEACHER')
        level = LevelFactory()
        term = TermFactory()

        resp = client.post(TIMETABLE_LIST, _timetable_payload(course, teacher, level, term))
        assert resp.status_code == status.HTTP_201_CREATED
        assert ClassTimetable.objects.count() == 1

    def test_student_cannot_create_timetable(self):
        student = UserFactory(role='STUDENT')
        client = auth_client(student)
        course = CourseFactory()
        teacher = UserFactory(role='TEACHER')
        level = LevelFactory()
        term = TermFactory()

        resp = client.post(TIMETABLE_LIST, _timetable_payload(course, teacher, level, term))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_teacher_cannot_create_timetable(self):
        teacher = UserFactory(role='TEACHER')
        client = auth_client(teacher)
        course = CourseFactory()
        level = LevelFactory()
        term = TermFactory()

        resp = client.post(TIMETABLE_LIST, _timetable_payload(course, teacher, level, term))
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_all_auth_can_list_timetables(self):
        ClassTimetableFactory()
        for role in ['STUDENT', 'TEACHER', 'ADMIN']:
            user = UserFactory(role=role)
            resp = auth_client(user).get(TIMETABLE_LIST)
            assert resp.status_code == status.HTTP_200_OK

    def test_unauthenticated_cannot_list(self):
        resp = APIClient().get(TIMETABLE_LIST)
        assert resp.status_code == status.HTTP_401_UNAUTHORIZED

    def test_admin_can_delete_timetable(self):
        admin = UserFactory(role='ADMIN')
        slot = ClassTimetableFactory()
        resp = auth_client(admin).delete(timetable_url(slot.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not ClassTimetable.objects.filter(pk=slot.pk).exists()

    def test_admin_can_patch_timetable(self):
        admin = UserFactory(role='ADMIN')
        slot = ClassTimetableFactory()
        resp = auth_client(admin).patch(timetable_url(slot.pk), {'room': 'R99'})
        assert resp.status_code == status.HTTP_200_OK
        slot.refresh_from_db()
        assert slot.room == 'R99'

    def test_filter_by_day(self):
        ClassTimetableFactory(day_of_week=ClassTimetable.MON)
        ClassTimetableFactory(day_of_week=ClassTimetable.TUE)
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).get(TIMETABLE_LIST + '?day_of_week=0')
        data = resp.data['data']
        assert len(data) == 1
        assert data[0]['day_of_week'] == 0


@pytest.mark.django_db
class TestTimetableConflict:

    def _create_slot(self, admin_client, course, teacher, level, term, room, day, start, end):
        return admin_client.post(TIMETABLE_LIST, _timetable_payload(
            course, teacher, level, term, room=room, day=day, start=start, end=end
        ))

    def test_same_room_same_time_returns_409(self):
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        course = CourseFactory()
        level = LevelFactory()
        term = TermFactory()
        teacher1 = UserFactory(role='TEACHER')
        teacher2 = UserFactory(role='TEACHER')

        resp1 = self._create_slot(client, course, teacher1, level, term, 'R1', 0, '08:00', '09:00')
        assert resp1.status_code == status.HTTP_201_CREATED

        resp2 = self._create_slot(client, course, teacher2, level, term, 'R1', 0, '08:00', '09:00')
        assert resp2.status_code == status.HTTP_409_CONFLICT
        assert 'room' in resp2.data['message']

    def test_same_teacher_same_time_returns_409(self):
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        course = CourseFactory()
        level = LevelFactory()
        term = TermFactory()
        teacher = UserFactory(role='TEACHER')

        resp1 = self._create_slot(client, course, teacher, level, term, 'R1', 0, '08:00', '09:00')
        assert resp1.status_code == status.HTTP_201_CREATED

        resp2 = self._create_slot(client, course, teacher, level, term, 'R2', 0, '08:00', '09:00')
        assert resp2.status_code == status.HTTP_409_CONFLICT
        assert 'teacher' in resp2.data['message']

    def test_same_room_different_day_returns_201(self):
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        course = CourseFactory()
        level = LevelFactory()
        term = TermFactory()
        teacher1 = UserFactory(role='TEACHER')
        teacher2 = UserFactory(role='TEACHER')

        resp1 = self._create_slot(client, course, teacher1, level, term, 'R1', 0, '08:00', '09:00')
        assert resp1.status_code == status.HTTP_201_CREATED

        resp2 = self._create_slot(client, course, teacher2, level, term, 'R1', 1, '08:00', '09:00')
        assert resp2.status_code == status.HTTP_201_CREATED

    def test_overlapping_time_detected(self):
        """08:00–10:00 and 09:00–11:00 overlap."""
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        course = CourseFactory()
        level = LevelFactory()
        term = TermFactory()
        teacher1 = UserFactory(role='TEACHER')
        teacher2 = UserFactory(role='TEACHER')

        self._create_slot(client, course, teacher1, level, term, 'R1', 0, '08:00', '10:00')
        resp = self._create_slot(client, course, teacher2, level, term, 'R1', 0, '09:00', '11:00')
        assert resp.status_code == status.HTTP_409_CONFLICT

    def test_adjacent_times_no_conflict(self):
        """End=09:00 and start=09:00 must not conflict."""
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        course = CourseFactory()
        level = LevelFactory()
        term = TermFactory()
        teacher1 = UserFactory(role='TEACHER')
        teacher2 = UserFactory(role='TEACHER')

        self._create_slot(client, course, teacher1, level, term, 'R1', 0, '08:00', '09:00')
        resp = self._create_slot(client, course, teacher2, level, term, 'R1', 0, '09:00', '10:00')
        assert resp.status_code == status.HTTP_201_CREATED

    def test_patch_room_conflict_returns_409(self):
        admin = UserFactory(role='ADMIN')
        client = auth_client(admin)
        term = TermFactory()
        teacher1 = UserFactory(role='TEACHER')
        teacher2 = UserFactory(role='TEACHER')
        slot1 = ClassTimetableFactory(room='R1', term=term, day_of_week=0,
                                       start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
                                       teacher=teacher1)
        slot2 = ClassTimetableFactory(room='R2', term=term, day_of_week=0,
                                       start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
                                       teacher=teacher2)
        # Try to move slot2 to R1 — should conflict with slot1
        resp = client.patch(timetable_url(slot2.pk), {'room': 'R1'})
        assert resp.status_code == status.HTTP_409_CONFLICT


# ---------------------------------------------------------------------------
# ExamSchedule tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestExamScheduleCRUD:

    def _payload(self, course=None, level=None, term=None):
        course = course or CourseFactory()
        level = level or LevelFactory()
        term = term or TermFactory()
        return {
            'course': str(course.pk),
            'level': str(level.pk),
            'term': str(term.pk),
            'exam_date': '2025-11-15',
            'start_time': '09:00',
            'end_time': '11:00',
            'room': 'Exam Hall 1',
            'exam_type': ExamSchedule.MID_TERM,
        }

    def test_admin_can_create_exam_schedule(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(EXAM_LIST, self._payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_student_cannot_create_exam_schedule(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).post(EXAM_LIST, self._payload())
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_all_auth_can_list(self):
        ExamScheduleFactory()
        for role in ['STUDENT', 'TEACHER', 'ADMIN']:
            user = UserFactory(role=role)
            resp = auth_client(user).get(EXAM_LIST)
            assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_delete(self):
        admin = UserFactory(role='ADMIN')
        exam = ExamScheduleFactory()
        resp = auth_client(admin).delete(exam_url(exam.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT

    def test_filter_by_exam_type(self):
        ExamScheduleFactory(exam_type=ExamSchedule.MID_TERM)
        ExamScheduleFactory(exam_type=ExamSchedule.END_OF_TERM)
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).get(EXAM_LIST + '?exam_type=MID_TERM')
        data = resp.data['data']
        assert len(data) == 1
        assert data[0]['exam_type'] == 'MID_TERM'


# ---------------------------------------------------------------------------
# Holiday tests
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestHolidayCRUD:

    def _payload(self, academic_year=None):
        academic_year = academic_year or AcademicYearFactory()
        return {
            'name': 'Christmas Break',
            'start_date': '2025-12-25',
            'end_date': '2026-01-02',
            'academic_year': str(academic_year.pk),
        }

    def test_admin_can_create_holiday(self):
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).post(HOLIDAY_LIST, self._payload())
        assert resp.status_code == status.HTTP_201_CREATED

    def test_student_cannot_create_holiday(self):
        student = UserFactory(role='STUDENT')
        resp = auth_client(student).post(HOLIDAY_LIST, self._payload())
        assert resp.status_code == status.HTTP_403_FORBIDDEN

    def test_all_auth_can_list(self):
        HolidayFactory()
        for role in ['STUDENT', 'TEACHER', 'ADMIN']:
            user = UserFactory(role=role)
            resp = auth_client(user).get(HOLIDAY_LIST)
            assert resp.status_code == status.HTTP_200_OK

    def test_admin_can_update_holiday(self):
        admin = UserFactory(role='ADMIN')
        holiday = HolidayFactory()
        resp = auth_client(admin).patch(holiday_url(holiday.pk), {'name': 'Updated Holiday'})
        assert resp.status_code == status.HTTP_200_OK
        holiday.refresh_from_db()
        assert holiday.name == 'Updated Holiday'

    def test_admin_can_delete_holiday(self):
        admin = UserFactory(role='ADMIN')
        holiday = HolidayFactory()
        resp = auth_client(admin).delete(holiday_url(holiday.pk))
        assert resp.status_code == status.HTTP_204_NO_CONTENT
        assert not Holiday.objects.filter(pk=holiday.pk).exists()

    def test_filter_by_academic_year(self):
        ay1 = AcademicYearFactory()
        ay2 = AcademicYearFactory()
        HolidayFactory(academic_year=ay1)
        HolidayFactory(academic_year=ay2)
        admin = UserFactory(role='ADMIN')
        resp = auth_client(admin).get(HOLIDAY_LIST + f'?academic_year={ay1.pk}')
        data = resp.data['data']
        assert len(data) == 1
