from django.db import transaction


class CourseOutlineService:

    @staticmethod
    @transaction.atomic
    def replace_weekly_topics(outline, topics_data):
        """Atomically replace all weekly topics on a course outline."""
        from apps.academics.models import WeeklyTopic

        outline.weekly_topics.all().delete()
        WeeklyTopic.objects.bulk_create(
            [WeeklyTopic(outline=outline, **topic) for topic in topics_data]
        )
        outline.save()
        return outline


class TransitionError(Exception):
    """Raised when a term transition cannot be performed."""


class TermTransitionService:
    """
    Advances the school term and handles per-student promotion/graduation.

    Rules (evaluated against the *current* term):
      Rule 1: term_number < 3 → set current is_current=False, set next term is_current=True.
              No student status changes.
      Rule 2: term_number == 3 AND student.level.number < 3 → promote student to next level.
              Term advances to term 1 of the next academic year.
      Rule 3: term_number == 3 AND student.level.number == 3 → set student.status = GRADUATED.
              Term advances to term 1 of the next academic year.
    """

    @staticmethod
    def transition():
        """
        Execute a single, atomic term transition.

        Returns:
            dict with keys: promoted (int), graduated (int), new_term (str UUID).

        Raises:
            TransitionError: if no current term, next term, or next academic year exists.
        """
        from apps.academics.models import AcademicYear, Level, Term
        from apps.enrollment.models import StudentProfile
        from apps.fees.tasks import generate_term_fees, mark_overdue_fees

        promoted = 0
        graduated = 0
        new_term = None

        with transaction.atomic():
            # Lock current term to prevent concurrent transitions
            current_term = (
                Term.objects
                .select_for_update()
                .filter(is_current=True)
                .first()
            )
            if current_term is None:
                raise TransitionError('No current term found.')

            old_term_id = current_term.id

            if current_term.term_number < 3:
                # Rule 1: advance within the same academic year
                next_term = (
                    Term.objects
                    .select_for_update()
                    .filter(
                        academic_year=current_term.academic_year,
                        term_number=current_term.term_number + 1,
                    )
                    .first()
                )
                if next_term is None:
                    raise TransitionError(
                        f'Term {current_term.term_number + 1} not found in academic year '
                        f'{current_term.academic_year.name}.'
                    )

                current_term.is_current = False
                current_term.save(update_fields=['is_current'])
                next_term.is_current = True
                next_term.save(update_fields=['is_current'])
                new_term = next_term

            else:
                # term_number == 3: end of year — advance to term 1 of next academic year
                next_year = (
                    AcademicYear.objects
                    .filter(start_date__gt=current_term.academic_year.end_date)
                    .order_by('start_date')
                    .first()
                )
                if next_year is None:
                    raise TransitionError('Next academic year not found.')

                next_term = (
                    Term.objects
                    .select_for_update()
                    .filter(academic_year=next_year, term_number=1)
                    .first()
                )
                if next_term is None:
                    raise TransitionError(
                        f'Term 1 not found in academic year {next_year.name}.'
                    )

                current_term.is_current = False
                current_term.save(update_fields=['is_current'])
                next_term.is_current = True
                next_term.save(update_fields=['is_current'])
                new_term = next_term

                # Lock all active students and apply Rules 2 & 3
                active_profiles = list(
                    StudentProfile.objects
                    .select_for_update()
                    .filter(status=StudentProfile.ACTIVE)
                    .select_related('level')
                )

                # Collect IDs per current level number
                level1_ids = [p.pk for p in active_profiles if p.level.number == 1]
                level2_ids = [p.pk for p in active_profiles if p.level.number == 2]
                level3_ids = [p.pk for p in active_profiles if p.level.number == 3]

                # Promote level 1 → 2
                if level1_ids:
                    level2 = Level.objects.get(number=2)
                    promoted += StudentProfile.objects.filter(pk__in=level1_ids).update(level=level2)

                # Promote level 2 → 3
                if level2_ids:
                    level3 = Level.objects.get(number=3)
                    promoted += StudentProfile.objects.filter(pk__in=level2_ids).update(level=level3)

                # Graduate level 3
                if level3_ids:
                    graduated = StudentProfile.objects.filter(pk__in=level3_ids).update(
                        status=StudentProfile.GRADUATED
                    )

            # Dispatch Celery tasks after the DB commit so they see committed data
            old_term_id_str = str(old_term_id)
            transaction.on_commit(lambda: mark_overdue_fees.delay(old_term_id_str))
            transaction.on_commit(lambda: generate_term_fees.delay())

        return {
            'promoted': promoted,
            'graduated': graduated,
            'new_term': str(new_term.id),
        }
