"""
Unit tests for TimetableService conflict detection.
"""
import datetime

import pytest

from apps.schedules.models import ClassTimetable
from apps.schedules.services import TimetableService
from tests.factories import (
    ClassTimetableFactory,
    CourseFactory,
    LevelFactory,
    TermFactory,
    UserFactory,
)


@pytest.mark.django_db
class TestTimetableConflictDetection:

    def _slot(self, room='R1', teacher=None, term=None, day=0,
               start='08:00', end='09:00'):
        teacher = teacher or UserFactory(role='TEACHER')
        term = term or TermFactory()
        return ClassTimetableFactory(
            room=room,
            teacher=teacher,
            term=term,
            day_of_week=day,
            start_time=datetime.time(*map(int, start.split(':'))),
            end_time=datetime.time(*map(int, end.split(':'))),
        )

    # ------------------------------------------------------------------
    # Room conflicts
    # ------------------------------------------------------------------

    def test_same_room_same_time_is_conflict(self):
        term = TermFactory()
        self._slot(room='R1', term=term, day=0, start='08:00', end='09:00')
        teacher2 = UserFactory(role='TEACHER')
        conflict = TimetableService.check_conflict(
            room='R1', teacher=teacher2, term=term, day_of_week=0,
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
        )
        assert conflict == 'room'

    def test_same_room_overlapping_time_is_conflict(self):
        term = TermFactory()
        self._slot(room='R1', term=term, day=0, start='08:00', end='10:00')
        teacher2 = UserFactory(role='TEACHER')
        conflict = TimetableService.check_conflict(
            room='R1', teacher=teacher2, term=term, day_of_week=0,
            start_time=datetime.time(9, 0), end_time=datetime.time(11, 0),
        )
        assert conflict == 'room'

    def test_same_room_different_day_no_conflict(self):
        term = TermFactory()
        self._slot(room='R1', term=term, day=0, start='08:00', end='09:00')
        teacher2 = UserFactory(role='TEACHER')
        conflict = TimetableService.check_conflict(
            room='R1', teacher=teacher2, term=term, day_of_week=1,
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
        )
        assert conflict is None

    def test_same_room_adjacent_times_no_conflict(self):
        """End of first == start of second — not an overlap."""
        term = TermFactory()
        self._slot(room='R1', term=term, day=0, start='08:00', end='09:00')
        teacher2 = UserFactory(role='TEACHER')
        conflict = TimetableService.check_conflict(
            room='R1', teacher=teacher2, term=term, day_of_week=0,
            start_time=datetime.time(9, 0), end_time=datetime.time(10, 0),
        )
        assert conflict is None

    def test_same_room_different_term_no_conflict(self):
        term1 = TermFactory()
        term2 = TermFactory()
        self._slot(room='R1', term=term1, day=0, start='08:00', end='09:00')
        teacher2 = UserFactory(role='TEACHER')
        conflict = TimetableService.check_conflict(
            room='R1', teacher=teacher2, term=term2, day_of_week=0,
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
        )
        assert conflict is None

    # ------------------------------------------------------------------
    # Teacher conflicts
    # ------------------------------------------------------------------

    def test_same_teacher_same_time_is_conflict(self):
        term = TermFactory()
        teacher = UserFactory(role='TEACHER')
        self._slot(room='R1', teacher=teacher, term=term, day=0, start='08:00', end='09:00')
        conflict = TimetableService.check_conflict(
            room='R2', teacher=teacher, term=term, day_of_week=0,
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
        )
        assert conflict == 'teacher'

    def test_same_teacher_different_day_no_conflict(self):
        term = TermFactory()
        teacher = UserFactory(role='TEACHER')
        self._slot(room='R1', teacher=teacher, term=term, day=0, start='08:00', end='09:00')
        conflict = TimetableService.check_conflict(
            room='R2', teacher=teacher, term=term, day_of_week=2,
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
        )
        assert conflict is None

    # ------------------------------------------------------------------
    # Update excludes self
    # ------------------------------------------------------------------

    def test_update_excludes_existing_slot(self):
        term = TermFactory()
        slot = self._slot(room='R1', term=term, day=0, start='08:00', end='09:00')
        # Updating same slot to same time should NOT conflict with itself
        conflict = TimetableService.check_conflict(
            room='R1', teacher=slot.teacher, term=term, day_of_week=0,
            start_time=datetime.time(8, 0), end_time=datetime.time(9, 0),
            exclude_pk=slot.pk,
        )
        assert conflict is None

    # ------------------------------------------------------------------
    # Service-level create / update
    # ------------------------------------------------------------------

    def test_service_create_returns_none_on_room_conflict(self):
        term = TermFactory()
        course = CourseFactory()
        level = LevelFactory()
        teacher = UserFactory(role='TEACHER')
        self._slot(room='R1', term=term, day=0, start='08:00', end='09:00')

        teacher2 = UserFactory(role='TEACHER')
        obj, conflict = TimetableService.create({
            'room': 'R1', 'teacher': teacher2, 'term': term,
            'day_of_week': 0,
            'start_time': datetime.time(8, 0),
            'end_time': datetime.time(9, 0),
            'course': course, 'level': level, 'class_section': '1A',
        })
        assert obj is None
        assert conflict == 'room'

    def test_service_create_succeeds_no_conflict(self):
        term = TermFactory()
        course = CourseFactory()
        level = LevelFactory()
        teacher = UserFactory(role='TEACHER')
        obj, conflict = TimetableService.create({
            'room': 'R99', 'teacher': teacher, 'term': term,
            'day_of_week': 0,
            'start_time': datetime.time(8, 0),
            'end_time': datetime.time(9, 0),
            'course': course, 'level': level, 'class_section': '1A',
        })
        assert conflict is None
        assert obj is not None
        assert ClassTimetable.objects.filter(pk=obj.pk).exists()
