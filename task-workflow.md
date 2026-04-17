# Task Workflow — School Management System Build

## Build Philosophy

* Phase-gated: each phase must pass its tests before the next begins
* Plan Mode (`Shift+Tab ×2`) before every new phase or complex feature
* `/clear` context between phases to prevent context bleed
* Every model → factory → serializer → service → view → tests, in that order

---

## Phase 0: Project Bootstrap

**Goal:** Runnable Django project with auth working end-to-end.

### Tasks

* [ ] Initialize Django project: `django-admin startproject config .`
* [ ] Install dependencies and freeze `requirements.txt`
* [ ] Configure `django-environ` — load from `.env`
* [ ] Configure PostgreSQL in `settings/base.py`, `settings/dev.py`, `settings/test.py`, `settings/prod.py`
* [ ] Configure Redis cache backend (`django-redis`)
* [ ] Configure Celery with Redis broker
* [ ] Create `apps/users/` app
  * [ ] `CustomUser` model:
    * [ ] `school_id` as `USERNAME_FIELD` (not email)
    * [ ] `must_change_password = BooleanField(default=True)`
    * [ ] `email` stored but not used for login
  * [ ] `Role` model + seed migration (6 roles)
  * [ ] `UserRole` M2M through model
  * [ ] `AuditLog` model (includes `FIRST_LOGIN_RESET` action)
* [ ] `UserService.create_user()`:
  * [ ] Accepts `first_name`, `last_name`, `email`, `password`, `roles`
  * [ ] Calls `generate_school_id(primary_role)` inside `select_for_update` transaction
  * [ ] Sets `must_change_password = True` — never bypassed
  * [ ] Logs `CREATE` to `AuditLog`
* [ ] `generate_school_id(primary_role)` service method with race-condition-safe `select_for_update`
* [ ] JWT auth: `djangorestframework-simplejwt`
  * [ ] Custom token serializer: inject `roles` and `must_change_password` into JWT claims
  * [ ] Login endpoint authenticates via `school_id` + password
  * [ ] Login response includes `force_password_reset: bool`
  * [ ] Blacklist app enabled for logout and token rotation
* [ ] `RequiresPasswordChange` permission class:
  * [ ] Blocks all endpoints when `must_change_password=True`
  * [ ] Exempts `POST /auth/first-login-reset/` and `POST /auth/logout/`
  * [ ] Returns HTTP 403 with `"message": "Password reset required before continuing."`
* [ ] `POST /auth/first-login-reset/` endpoint:
  * [ ] Validates new password (min 8 chars, 1 uppercase, 1 digit)
  * [ ] Rejects if new password matches the admin-set one
  * [ ] Sets `must_change_password = False`
  * [ ] Blacklists restricted token, issues fresh unrestricted JWT pair
  * [ ] Logs `FIRST_LOGIN_RESET` to `AuditLog`
* [ ] `BaseRolePermission` base class
* [ ] `has_role()`, `has_any_role()`, `get_cached_roles()` on `CustomUser`
* [ ] `UserFactory` (uses `school_id` sequence, `must_change_password=False` by default in tests)
* [ ] `RoleFactory` in `tests/factories/`
* [ ] Tests:
  * [ ] Login with `school_id` succeeds, email login rejected
  * [ ] New user: `must_change_password=True`
  * [ ] Login when `must_change_password=True` → `force_password_reset: true` in response
  * [ ] Restricted token cannot access `/students/` → 403
  * [ ] Restricted token CAN access `/auth/first-login-reset/`
  * [ ] Successful reset → `must_change_password=False`, fresh tokens returned
  * [ ] New password same as old → 400 error
  * [ ] `generate_school_id` produces `STD001`, `STD002` sequentially with no gaps
  * [ ] Concurrent `create_user` calls don't produce duplicate `school_id` (transaction test)
  * [ ] Role caching and multi-role union correct
  * [ ] IT Support reset sets `must_change_password=True` → user forced through reset on next login

**Gate:** `pytest tests/unit/users/ tests/integration/auth/` all green.
`school_id` generation is sequential with no duplicates under concurrent load.
First-login reset flow end-to-end verified. Restricted token correctly blocked on all non-exempt endpoints.

---

## Phase 1: Academic Structure

**Goal:** Programs, courses, levels, terms, academic years all modelled and CRUD'd.

### Tasks

* [ ] `apps/academics/` app
  * [ ] `AcademicYear` model + CRUD
  * [ ] `Term` model + CRUD (3 per year)
  * [ ] `Level` model + seed migration (3 levels)
  * [ ] `Program` model + seed migration (5 programs)
  * [ ] `Course` model (CORE + ELECTIVE) + seed migration (7 core courses)
  * [ ] `TeacherCourseAssignment` model + CRUD
  * [ ] `CourseOutline` + `WeeklyTopic` models + CRUD
* [ ] All serializers with `select_related` on querysets
* [ ] Filter backends: `?type=CORE&program=uuid`
* [ ] Cache: `program:{id}:courses` (1 hour)
* [ ] Tests: CRUD permissions (admin vs student), course type filtering

**Gate:** All academic endpoints return correct data. Cache hit verified.

---

## Phase 2: Students & Enrollment

**Goal:** Student lifecycle, program assignment, auto-enrollment in core courses.

### Tasks

* [ ] `apps/enrollment/` app
  * [ ] `StudentProfile` model (OneToOne with `CustomUser`)
  * [ ] `Enrollment` model with `UNIQUE(student, course, term, level)`
  * [ ] `EnrollmentService.enroll_core_courses()` — bulk_create with ignore_conflicts
  * [ ] `EnrollmentService.enroll_electives()` — validates exactly 4 courses
* [ ] Signal: `post_save` on `StudentProfile(created=True)` → auto-enroll core
* [ ] Student endpoints: list, detail, assign-program, enroll-electives, courses
* [ ] `StudentProfileFactory`, `EnrollmentFactory`
* [ ] Tests:
  * [ ] Create student → assert 7 core enrollments created
  * [ ] Re-trigger signal → assert no duplicate enrollments (idempotent)
  * [ ] Enroll electives < 4 → 400 error
  * [ ] Enroll electives > 4 → 400 error
  * [ ] Enroll electives from wrong program → 400 error
  * [ ] N+1 check on `GET /students/` with 50 students

**Gate:** Auto-enrollment signal works. Constraint enforced. N+1 clean.

---

## Phase 3: Teacher Assignment & Course Content

**Goal:** Teachers can be assigned to courses and upload content.

### Tasks

* [ ] `TeacherProfile` (or extend `UserRole` + teacher-specific endpoints)
* [ ] `POST /courses/{id}/assign-teacher/` endpoint
* [ ] `Resource` model + upload endpoint (S3 via django-storages)
  * [ ] MIME validation with `python-magic`
  * [ ] File size validation (50MB max)
  * [ ] Pre-signed URL generation on read
* [ ] `CourseOutline` + `WeeklyTopic` CRUD endpoints
* [ ] Object-level permission: teacher can only manage own course content
* [ ] `UploadThrottle` (10/hour) on upload endpoints
* [ ] Tests:
  * [ ] Teacher A cannot edit Teacher B's course resources
  * [ ] Invalid MIME type rejected
  * [ ] File > 50MB rejected
  * [ ] Course outline by week renders correctly

**Gate:** Teacher content management works. Object-level permissions enforced.

---

## Phase 4: Assessments — Quiz

**Goal:** Full quiz lifecycle with auto-close.

### Tasks

* [ ] `apps/assessments/` — Quiz models
  * [ ] `Quiz`, `Question`, `QuestionChoice`
  * [ ] `QuizAttempt`, `QuizAnswer`
* [ ] Quiz CRUD endpoints (teacher)
* [ ] `POST /quizzes/{id}/publish/`
* [ ] `POST /quizzes/{id}/attempts/` — start attempt
* [ ] `POST /quiz-attempts/{id}/submit/` — submit + auto-grade
  * [ ] MC + TF + MULTIPLE_ANSWER auto-graded
  * [ ] SHORT_ANSWER stored, graded manually by teacher later
* [ ] Celery task: `close_expired_quizzes` (every 5 min Beat)
  * [ ] Index on `(status, due_datetime)`
* [ ] Live check in submit view: reject if closed or past due
* [ ] Tests:
  * [ ] Attempt after max_attempts → 422
  * [ ] Submit after due_datetime → 422
  * [ ] Quiz auto-closes 5 min after due (Celery eager mode)
  * [ ] Auto-grade MC: correct choice → full marks
  * [ ] Auto-grade MULTIPLE_ANSWER: partial selections → 0 (or partial credit, specify rule)
  * [ ] Attempt limit per student enforced even on race condition (db constraint)

**Gate:** Quiz lifecycle complete. Auto-close verified. Attempt limits enforced.

---

## Phase 5: Assessments — Assignment

**Goal:** Assignment submission and grading.

### Tasks

* [ ] `Assignment`, `AssignmentSubmission` models
* [ ] Assignment CRUD (teacher)
* [ ] `POST /course-assignments/{id}/submit/` (student: file or text)
* [ ] `PATCH /assignment-submissions/{id}/grade/` (teacher)
* [ ] Celery task: `close_expired_assignments`
* [ ] `TeacherEvaluation` model + endpoint (student → teacher, one per term)
* [ ] Tests:
  * [ ] Submit to closed assignment → 422
  * [ ] Student cannot submit twice for same assignment (409)
  * [ ] File submission stored to S3 (mock in tests)
  * [ ] Evaluation uniqueness enforced

**Gate:** Full assignment lifecycle. Evaluation endpoint works.

---

## Phase 6: Term Transition

**Goal:** Admin can advance the academic calendar with all downstream effects.

### Tasks

* [ ] `TermTransitionService` with `select_for_update`
  * [ ] Advance term (< 3): update `is_current`
  * [ ] Promote level (term 3, level < 3): update student level, reset term
  * [ ] Graduate (term 3, level 3): set `status=GRADUATED`
  * [ ] All in one `transaction.atomic()`
* [ ] Celery tasks called after transition: `mark_overdue_fees`, `generate_term_fees`
* [ ] `POST /api/v1/terms/transition/` endpoint (Admin only, throttle 2/hour)
* [ ] Tests:
  * [ ] Term 1 → Term 2: student term increments, level unchanged
  * [ ] Term 3, Level 1 → Term 1, Level 2
  * [ ] Term 3, Level 3 → status=GRADUATED
  * [ ] Concurrent transition calls blocked by `select_for_update`
  * [ ] Unpaid fees marked OVERDUE after transition
  * [ ] New term fee records generated

**Gate:** All 3 transition scenarios tested. Transaction safety verified.

---

## Phase 7: Fees

**Goal:** Fee structures, invoices, payments, overdue detection.

### Tasks

* [ ] `FeeStructure`, `AdditionalFee`, `StudentFee`, `Payment` models
* [ ] `FeeCalculationService.calculate_for_student()`
* [ ] `StudentFee.save()` — status auto-computation
* [ ] Fee CRUD endpoints (Admin)
* [ ] Payment recording endpoint
* [ ] `GET /student-fees/` with filters (by status, term, level)
* [ ] `POST /student-fees/send-reminder/` → Celery task
* [ ] Fee structure cache + invalidation
* [ ] Tests:
  * [ ] Base + additional fee aggregated correctly
  * [ ] Payment → PARTIALLY_PAID → FULLY_PAID status flow
  * [ ] No re-payment beyond total_amount (or allow overpayment if spec unclear)
  * [ ] OVERDUE set on transition

**Gate:** Fee lifecycle complete. Overdue logic verified.

---

## Phase 8: Schedules & Announcements

**Goal:** Admin-managed schedules. Multi-target announcements.

### Tasks

* [ ] `ClassTimetable`, `ExamSchedule`, `Holiday` CRUD
* [ ] Timetable conflict detection (same room, same time) at service layer
* [ ] `Announcement`, `AnnouncementRecipient` models
* [ ] Announcement create + publish flow
* [ ] Celery task: fan-out `AnnouncementRecipient` rows on publish
* [ ] Recipient filtering logic (ALL, BY_PROGRAM, BY_LEVEL, etc.)
* [ ] `GET /announcements/` — user sees own only, annotated with `is_read`
* [ ] `POST /announcements/{id}/read/`
* [ ] Tests:
  * [ ] Admin announcement to ALL → all users get recipient record
  * [ ] BY_PROGRAM → only students of that program
  * [ ] Student cannot see announcement not addressed to them
  * [ ] Unread count correct

**Gate:** Announcement fan-out works. Recipient scoping correct.

---

## Phase 9: Reports & IT Support

**Goal:** Report generation, export, IT support workflows.

### Tasks

* [ ] `GET /reports/academic-performance/` — annotated queryset
* [ ] `GET /reports/fee-collection/` — aggregation
* [ ] `POST /reports/export/` → Celery task → S3 → presigned URL
* [ ] `ReportTask` model to track export status
* [ ] IT Support: `SupportTicket` CRUD
* [ ] IT Support: `POST /support/reset-password/` + audit log
* [ ] Tests:
  * [ ] Report aggregations are numerically correct (use fixtures)
  * [ ] Export task produces valid CSV
  * [ ] Password reset logged to AuditLog
  * [ ] Student cannot access another student's report

**Gate:** Reports accurate. Export async flow works. Audit logged.

---

## Phase 10: Security Hardening & Production Readiness

### Tasks

* [ ] Throttle classes configured and tested for all endpoint groups
* [ ] `nplusone` removed from production settings, only in test
* [ ] `django-silk` removed from production settings
* [ ] CORS: restrict to known frontend origins
* [ ] Security headers: `SECURE_HSTS_SECONDS`, `SECURE_CONTENT_TYPE_NOSNIFF`, etc.
* [ ] `DEBUG=False` enforcement in production settings
* [ ] All secrets via environment — CI scans for hardcoded secrets
* [ ] `ruff` + `mypy` pass with zero errors
* [ ] Coverage report: all apps ≥ 85%
* [ ] Load test: `locust` or `k6` against staging
* [ ] `CHANGELOG.md` + API versioning confirmed

**Gate:** Zero security warnings. Coverage target met. Load test baseline established.

---

## Context Management Rules

| Situation                    | Action                                                             |
| ---------------------------- | ------------------------------------------------------------------ |
| Starting a new phase         | `/clear`then paste the phase tasks                               |
| Switching to a different app | `/clear`                                                         |
| After 2+ hours of work       | Manual `/compact`then continue                                   |
| Bug in previous phase        | Fix in isolation, re-run that phase's tests                        |
| Investigating a bug          | Scope narrowly — don't ask Claude to "explore the whole codebase" |

---

## Definition of Done (per feature)

* [ ] Model created with correct fields, constraints, indexes
* [ ] Factory created in `tests/factories/`
* [ ] Service layer handles business logic
* [ ] Serializer validates input
* [ ] ViewSet with correct `get_queryset()` (no N+1)
* [ ] Permission class applied
* [ ] Throttle class applied (if applicable)
* [ ] Unit tests pass
* [ ] Integration tests pass (auth, permissions, happy path, edge cases)
* [ ] Coverage does not drop below phase target
