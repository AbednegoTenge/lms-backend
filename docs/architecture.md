# Architecture — School Management System

## Overview

The SMS backend is a Django REST Framework monolith structured as a set of
bounded-context Django apps. Each app owns its models, serializers, views,
services, signals, and tasks. The system is designed to scale vertically first
(Postgres + Redis), with Celery handling all async work.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         Clients                             │
│              (Web App · Mobile App · Admin UI)              │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTPS
┌──────────────────────────▼──────────────────────────────────┐
│                      Nginx (Reverse Proxy)                  │
│              Rate limiting · TLS termination                │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│              Django + DRF Application Server                │
│                  (Gunicorn, 4–8 workers)                    │
│                                                             │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │  users   │ │academics │ │enrollment│ │ assessments  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │   fees   │ │schedules │ │announce- │ │  it_support  │   │
│  │          │ │          │ │  ments   │ │              │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│                    ┌──────────────┐                         │
│                    │   reports    │                         │
│                    └──────────────┘                         │
└────────────┬────────────────────────────────────────────────┘
             │
   ┌──────────┼───────────┬────────────┐
   ▼          ▼           ▼            ▼
┌──────┐  ┌──────┐  ┌─────────┐  ┌────────┐
│  PG  │  │Redis │  │ Celery  │  │  S3    │
│  DB  │  │Cache │  │ Worker  │  │ Media  │
│      │  │+Queue│  │  +Beat  │  │        │
└──────┘  └──────┘  └─────────┘  └────────┘
```

---

## Django App Boundaries

### `users`

Owns `CustomUser`, `Role`, `UserRole` (M2M through table). Handles JWT auth,
password management, and multi-role resolution. No business logic from other
domains allowed here.

### `academics`

Owns `AcademicYear`, `Term`, `Level`, `Program`, `Course` (both core and
elective), `CourseOutline`, `WeeklyTopic`. Responsible for term transition
logic via a service layer.

### `enrollment`

Owns `Enrollment`, `ProgramEnrollment`. Listens to signals from `users` and
`academics`. Auto-enrolls students in core courses. Enforces the 4-elective
constraint.

### `assessments`

Owns `Quiz`, `Question`, `QuestionChoice`, `Assignment`, `QuizAttempt`,
`QuizSubmission`, `AssignmentSubmission`, `TeacherEvaluation`. Celery tasks
handle auto-close on due date.

### `fees`

Owns `FeeStructure`, `AdditionalFee`, `StudentFee`, `Payment`. Term transition
hook updates overdue status. Admin can attach custom fee line items.

### `schedules`

Owns `ClassTimetable`, `ExamSchedule`, `Holiday`, `Vacation`. Admin CRUD.
No async tasks needed.

### `announcements`

Owns `Announcement`, `AnnouncementRecipient`. Supports broadcast rules
(all, by role, by class, by program, specific user).

### `reports`

Read-only views. Aggregates from `enrollment`, `assessments`, `fees`.
Uses raw SQL / `annotate` for performance. No owned models.

### `it_support`

Owns `SupportTicket`, `PasswordResetRequest`. IT Support role actions.

---

## Request Lifecycle

```
Client Request
     │
     ▼
Nginx (rate limit check, static/media shortcircuit)
     │
     ▼
Gunicorn → Django WSGI
     │
     ▼
SecurityMiddleware → SessionMiddleware → CORSMiddleware
     │
     ▼
JWTAuthentication (validates token, loads user + roles)
     │
     ▼
DRF Router → ViewSet
     │
     ▼
Permission classes (RolePermission checks union of user roles)
     │
     ▼
Throttle classes (per-user or anon rate limits)
     │
     ▼
Serializer validation
     │
     ▼
Service layer (business logic, DB writes)
     │
     ▼
Signal dispatch (if needed: e.g., auto-enrollment)
     │
     ▼
Celery task enqueue (if async work needed)
     │
     ▼
Response → { success, data, message }
```

---

## Async / Background Work (Celery)

| Task                                | Trigger            | Schedule        |
| ----------------------------------- | ------------------ | --------------- |
| `close_expired_quizzes`           | Celery Beat        | Every 5 minutes |
| `close_expired_assignments`       | Celery Beat        | Every 5 minutes |
| `send_announcement_notifications` | On create          | Async           |
| `generate_term_fee_invoices`      | On term transition | Async           |
| `mark_overdue_fees`               | On term transition | Async           |
| `send_fee_reminder`               | Admin action       | Async           |
| `export_report_csv`               | Admin action       | Async           |

---

## Caching Strategy (Redis)

| Cache Key Pattern                   | TTL    | Invalidated On       |
| ----------------------------------- | ------ | -------------------- |
| `program:{id}:courses`            | 1 hour | Course add/remove    |
| `user:{id}:roles`                 | 15 min | Role change          |
| `course:{id}:outline`             | 30 min | Outline update       |
| `student:{id}:enrolled_courses`   | 10 min | Enrollment change    |
| `fee_structure:{level}:{program}` | 1 hour | Fee structure update |
| `announcement:list:{role}`        | 5 min  | Announcement create  |

Use `django.core.cache` with Redis backend. Cache at the view level with
`@cache_page` only for truly static data. Prefer queryset-level caching
with `django-cachalot` for ORM queries.

---

## Database Strategy

### Connection Pooling

Use `django-db-geventpool` or PgBouncer in front of PostgreSQL.
Pool size: 20 connections per Gunicorn worker.

### Indexes (beyond default PKs/FKs)

```sql
-- Enrollment lookups
CREATE INDEX idx_enrollment_student_course ON enrollment_enrollment(student_id, course_id);
CREATE INDEX idx_enrollment_status ON enrollment_enrollment(status);

-- Quiz/Assignment status + due date (for Celery auto-close query)
CREATE INDEX idx_quiz_status_due ON assessments_quiz(status, due_datetime);
CREATE INDEX idx_assignment_status_due ON assessments_assignment(status, due_datetime);

-- Fee lookups by term
CREATE INDEX idx_studentfee_student_term ON fees_studentfee(student_id, term_id);
CREATE INDEX idx_studentfee_status ON fees_studentfee(payment_status);

-- Announcement recipient lookup
CREATE INDEX idx_announcement_recipient ON announcements_announcementrecipient(user_id, announcement_id);

-- Audit log
CREATE INDEX idx_auditlog_user_timestamp ON users_auditlog(user_id, timestamp DESC);
```

### Read Replicas (future)

Route report queries and CSV exports to a read replica using
`DATABASE_ROUTERS` in Django settings.

---

## Security Architecture

### Authentication

* JWT access token: 15 minute TTL
* JWT refresh token: 7 day TTL, stored in HttpOnly cookie
* Token blacklist on logout (`djangorestframework-simplejwt` blacklist app)

### Authorization

* Custom `BaseRolePermission` class per endpoint
* Multi-role union: user passes if ANY assigned role grants permission
* Object-level permissions for student-owns-submission, teacher-owns-course

### Rate Limiting (DRF Throttling)

```python
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/min',
        'user': '200/min',
        'auth': '5/min',      # login, refresh, password reset
        'upload': '10/hour',  # file upload endpoints
    }
}
```

### Input Validation

* File uploads: check MIME type with `python-magic`, reject non-whitelisted types
* Max file size: 50MB enforced at Nginx and Django layer
* All UUIDs validated before DB lookup (prevents 500 on malformed IDs)
* SQL injection: ORM only, no raw string interpolation

### Audit Logging

Every write action by admin/principal/IT support logs to `AuditLog`:
`{ user, action, model, object_id, payload_diff, ip_address, timestamp }`

---

## Scalability Path

| Stage            | Action                                                     |
| ---------------- | ---------------------------------------------------------- |
| Now              | Single server, Postgres + Redis on same host               |
| 500+ concurrent  | Separate DB server, Redis server; add Gunicorn workers     |
| 2000+ concurrent | PgBouncer, read replica for reports, CDN for media         |
| 10000+           | Horizontal app scaling behind load balancer, Redis Cluster |

---

## Media File Strategy

* Student assignment uploads → S3 bucket (`sms-submissions/`)
* Teacher resources → S3 bucket (`sms-resources/`)
* Generated reports → S3 bucket (`sms-reports/`) with 24h signed URL
* Local dev: `MEDIA_ROOT` on disk via `django-storages` with `FileSystemStorage`
* All S3 URLs are pre-signed with 1h expiry — never expose raw bucket URLs

---

## Environment Configuration

```
# .env (never commit)
SECRET_KEY=
DEBUG=False
DATABASE_URL=postgres://user:pass@host:5432/sms
REDIS_URL=redis://host:6379/0
CELERY_BROKER_URL=redis://host:6379/1
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
ALLOWED_HOSTS=
CORS_ALLOWED_ORIGINS=
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=15
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7
```
