from django.db import transaction

from apps.academics.models import Course, Term
from apps.enrollment.models import Enrollment


class EnrollmentService:

    @staticmethod
    def enroll_core_courses(student, term, level):
        """Auto-enroll student in all active CORE courses for the given term/level.

        Uses bulk_create with ignore_conflicts=True so repeated calls are idempotent.
        Returns the number of new enrollments created.
        """
        core_courses = Course.objects.filter(course_type=Course.CORE, is_active=True)

        enrollments = [
            Enrollment(
                student=student,
                course=course,
                term=term,
                level=level,
                enrollment_type=Enrollment.CORE,
                enrolled_by=None,
            )
            for course in core_courses
        ]

        created = Enrollment.objects.bulk_create(enrollments, ignore_conflicts=True)
        return len(created)

    @staticmethod
    @transaction.atomic
    def enroll_electives(student, course_ids, term, level, enrolled_by=None):
        """Enroll student in exactly 4 elective courses from their program.

        Raises ValueError for any business rule violation.
        Returns the number of enrollments created.
        """
        profile = student.student_profile

        if profile.program is None:
            raise ValueError('Student does not have a program assigned.')

        if len(course_ids) != 4:
            raise ValueError(f'Exactly 4 elective courses required; got {len(course_ids)}.')

        courses = list(
            Course.objects.filter(
                id__in=course_ids,
                course_type=Course.ELECTIVE,
                is_active=True,
            ).select_related('program')
        )

        if len(courses) != 4:
            raise ValueError('One or more course IDs are invalid or not active elective courses.')

        wrong_program = [c for c in courses if c.program_id != profile.program_id]
        if wrong_program:
            names = ', '.join(c.code for c in wrong_program)
            raise ValueError(
                f'Courses {names} do not belong to the student\'s program '
                f'({profile.program.get_name_display()}).'
            )

        enrollments = [
            Enrollment(
                student=student,
                course=course,
                term=term,
                level=level,
                enrollment_type=Enrollment.ELECTIVE,
                enrolled_by=enrolled_by,
            )
            for course in courses
        ]

        created = Enrollment.objects.bulk_create(enrollments, ignore_conflicts=True)
        return len(created)
