# School Management System — Claude Code Configuration

## Project Overview

Django REST Framework backend for a school management system with RBAC, academic
management, assessments, fee collection, and announcements.

## Tech Stack

* **Runtime:** Python 3.12
* **Framework:** Django 5.x + Django REST Framework 3.15
* **Database:** PostgreSQL 16
* **Cache:** Redis 7 (django-redis)
* **Task Queue:** Celery 5 + Redis broker
* **Auth:** JWT via djangorestframework-simplejwt
* **Search:** django-filter
* **Storage:** django-storages + AWS S3 (media files)
* **Testing:** pytest-django + factory-boy + faker

## Commands

```bash
# Setup
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Database
python manage.py migrate
python manage.py seed_data          # load fixtures (programs, core courses)

# Run
python manage.py runserver
celery -A config worker -l info     # background tasks
celery -A config beat -l info       # scheduled tasks (quiz/assignment auto-close)

# Testing
pytest                              # full suite
pytest tests/unit/                  # unit only
pytest tests/integration/           # integration only
pytest -k "test_enrollment"         # single test by name
pytest --cov=apps --cov-report=html # coverage report

# Linting
ruff check .
ruff format .
mypy apps/
```

## Project Structure

```
config/             # Django settings, urls, celery, wsgi
apps/
  users/            # CustomUser, multi-role support
  academics/        # Programs, Courses, Levels, Terms, AcademicYear
  enrollment/       # Enrollment, CoreCourseAutoEnrollment signal
  assessments/      # Quiz, Assignment, Submission, Question
  fees/             # FeeStructure, StudentFee, Payment
  schedules/        # Timetable, ExamSchedule, Holiday
  announcements/    # Announcement, Recipient
  reports/          # Report generation views
  it_support/       # PasswordReset, IssueTicket
tests/
  unit/
  integration/
  factories/        # factory-boy factories
docs/               # all .md documentation
```

## Code Style

* Snake_case for models, fields, variables
* PascalCase for classes
* All API responses: `{ "success": bool, "data": {}, "message": "" }`
* UUID primary keys on ALL models (use `import uuid; models.UUIDField(default=uuid.uuid4)`)
* Use `select_related` / `prefetch_related` on EVERY queryset that touches FK/M2M — no N+1
* All views use DRF `ModelViewSet` unless there's a specific reason not to
* Permissions live in `apps/<app>/permissions.py` — never inline in views
* Signals live in `apps/<app>/signals.py` — never inline in models
* All Celery tasks in `apps/<app>/tasks.py`
* Never put business logic in serializers — use service layer in `apps/<app>/services.py`

## Critical Business Rules (NEVER violate)

* **Login uses `school_id`, not email** — `USERNAME_FIELD = 'school_id'` on `CustomUser`
* **`school_id` is server-generated** from primary role prefix + zero-padded sequence (STD001, TCH003, ADM001, PRI001, IT002, SA001). Admin never supplies it.
* **`school_id` generation is transactional** — use `select_for_update` to prevent race conditions on concurrent user creation
* **Admin sets the initial password** at user creation — no auto-generation
* **`must_change_password = True` on every new account** — set in `UserService.create_user()`, never bypassed
* **First-login token is restricted** — when `must_change_password=True`, issued JWT only permits `POST /auth/first-login-reset/`. All other endpoints return HTTP 403 via `RequiresPasswordChange` permission class
* **IT Support reset re-triggers first-login flow** — sets `must_change_password=True` so user must reset again
* Core courses auto-enroll via signal — never call enrollment logic directly from views
* Exactly 4 elective courses per student per program — enforce at serializer + DB level
* Term transitions only via dedicated admin endpoint — never ad-hoc field updates
* Quiz/assignment auto-close runs via Celery beat — status is computed, never manually set
* IT Support accounts created only by Super Admin
* Multi-role users: permissions are the UNION of all assigned roles
* Fee becomes OVERDUE automatically on term transition if status != FULLY_PAID
* Graduated students (Level 3, Term 3 transition) are read-only — no re-enrollment

## Security Rules

* NEVER hardcode secrets — use environment variables via django-environ
* NEVER commit `.env` files
* NEVER disable CSRF for non-API routes
* Rate limiting on ALL auth endpoints (django-ratelimit or DRF throttling)
* File uploads: validate MIME type server-side, reject executables
* All admin actions logged to AuditLog model

## Testing Rules

* Every new model needs a factory in `tests/factories/`
* Every new endpoint needs at least: auth test, permission test, happy path, edge case
* Mock Celery tasks in unit tests with `@override_settings(CELERY_TASK_ALWAYS_EAGER=True)`
* Use `pytest.mark.django_db` — never `TestCase` unless unavoidable
* Target 85%+ coverage on `apps/`

## N+1 Prevention

* Always use `select_related` for FK fields accessed in serializers
* Always use `prefetch_related` for M2M or reverse FK accessed in serializers
* Run `django-silk` in dev to catch slow queries
* Add `nplusone` middleware in test settings to catch N+1 automatically

## Import Order (enforced by ruff)

1. Standard library
2. Django
3. DRF
4. Third-party
5. Local apps (absolute imports only)

## @imports

* API contracts: @docs/api.md
* Data models: @docs/models.md
* Permissions matrix: @docs/permissions.md
* Architecture: @docs/architecture.md
