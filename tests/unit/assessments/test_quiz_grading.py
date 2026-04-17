"""Unit tests for quiz auto-grading logic."""
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.assessments.models import Question, QuizAttempt
from apps.assessments.views import _grade_attempt


def _make_question(q_type, marks, correct_ids, all_choice_ids):
    """Build a mock Question object with choices."""
    q = MagicMock(spec=Question)
    q.question_type = q_type
    q.marks = Decimal(str(marks))

    correct_qs = MagicMock()
    correct_qs.values_list.return_value = correct_ids
    q.choices.filter.return_value = correct_qs
    return q


def _make_attempt(answers):
    """Build a mock QuizAttempt with pre-built answers."""
    attempt = MagicMock(spec=QuizAttempt)
    attempt.answers.prefetch_related.return_value.select_related.return_value = answers
    return attempt


@pytest.mark.django_db
class TestAutoGrading:
    def test_multiple_choice_correct(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=10)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.MULTIPLE_CHOICE,
            marks=Decimal('5.00'),
            order=1,
        )
        correct_choice = QuestionChoiceFactory(question=question, is_correct=True)
        QuestionChoiceFactory(question=question, is_correct=False)

        attempt = QuizAttemptFactory(quiz=quiz)
        answer = QuizAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_choices.set([correct_choice])

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('5.00')
        assert attempt.status == QuizAttempt.GRADED

    def test_multiple_choice_wrong(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=10)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.MULTIPLE_CHOICE,
            marks=Decimal('5.00'),
            order=1,
        )
        QuestionChoiceFactory(question=question, is_correct=True)
        wrong_choice = QuestionChoiceFactory(question=question, is_correct=False)

        attempt = QuizAttemptFactory(quiz=quiz)
        answer = QuizAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_choices.set([wrong_choice])

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('0.00')
        assert attempt.status == QuizAttempt.GRADED

    def test_true_false_correct(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=4)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.TRUE_FALSE,
            marks=Decimal('2.00'),
            order=1,
        )
        true_choice = QuestionChoiceFactory(question=question, text='True', is_correct=True)
        QuestionChoiceFactory(question=question, text='False', is_correct=False)

        attempt = QuizAttemptFactory(quiz=quiz)
        answer = QuizAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_choices.set([true_choice])

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('2.00')

    def test_multiple_answer_all_correct(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=10)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.MULTIPLE_ANSWER,
            marks=Decimal('4.00'),
            order=1,
        )
        c1 = QuestionChoiceFactory(question=question, is_correct=True)
        c2 = QuestionChoiceFactory(question=question, is_correct=True)
        QuestionChoiceFactory(question=question, is_correct=False)

        attempt = QuizAttemptFactory(quiz=quiz)
        answer = QuizAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_choices.set([c1, c2])

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('4.00')

    def test_multiple_answer_partial_gets_zero(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=10)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.MULTIPLE_ANSWER,
            marks=Decimal('4.00'),
            order=1,
        )
        c1 = QuestionChoiceFactory(question=question, is_correct=True)
        QuestionChoiceFactory(question=question, is_correct=True)  # c2, not selected
        QuestionChoiceFactory(question=question, is_correct=False)

        attempt = QuizAttemptFactory(quiz=quiz)
        answer = QuizAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_choices.set([c1])  # only 1 of 2 correct choices

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('0.00')

    def test_multiple_answer_includes_wrong_gets_zero(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=10)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.MULTIPLE_ANSWER,
            marks=Decimal('4.00'),
            order=1,
        )
        c1 = QuestionChoiceFactory(question=question, is_correct=True)
        c2 = QuestionChoiceFactory(question=question, is_correct=True)
        wrong = QuestionChoiceFactory(question=question, is_correct=False)

        attempt = QuizAttemptFactory(quiz=quiz)
        answer = QuizAnswer.objects.create(attempt=attempt, question=question)
        answer.selected_choices.set([c1, c2, wrong])  # all correct + a wrong

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('0.00')

    def test_short_answer_stays_submitted(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=10)
        question = QuestionFactory(
            quiz=quiz,
            question_type=Question.SHORT_ANSWER,
            marks=Decimal('5.00'),
            order=1,
        )

        attempt = QuizAttemptFactory(quiz=quiz)
        QuizAnswer.objects.create(attempt=attempt, question=question, text_answer='my answer')

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.status == QuizAttempt.SUBMITTED
        assert attempt.score == Decimal('0.00')  # no graded points

    def test_mixed_questions_short_answer_keeps_submitted_status(self, db):
        from tests.factories import (
            OpenQuizFactory,
            QuestionChoiceFactory,
            QuestionFactory,
            QuizAttemptFactory,
        )
        from apps.assessments.models import QuizAnswer

        quiz = OpenQuizFactory(total_marks=15)
        mc_q = QuestionFactory(quiz=quiz, question_type=Question.MULTIPLE_CHOICE, marks=Decimal('5.00'), order=1)
        correct = QuestionChoiceFactory(question=mc_q, is_correct=True)
        QuestionChoiceFactory(question=mc_q, is_correct=False)
        sa_q = QuestionFactory(quiz=quiz, question_type=Question.SHORT_ANSWER, marks=Decimal('10.00'), order=2)

        attempt = QuizAttemptFactory(quiz=quiz)
        mc_ans = QuizAnswer.objects.create(attempt=attempt, question=mc_q)
        mc_ans.selected_choices.set([correct])
        QuizAnswer.objects.create(attempt=attempt, question=sa_q, text_answer='explain...')

        _grade_attempt(attempt)
        attempt.refresh_from_db()

        assert attempt.score == Decimal('5.00')
        assert attempt.status == QuizAttempt.SUBMITTED
