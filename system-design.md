# System Design — School Management System

## 1. Core Domain Breakdown

The system is divided into 9 bounded contexts, each as a Django app:

```
users          → Identity, multi-role, auth
academics      → Programs, courses, levels, terms, outlines
enrollment     → Student ↔ course relationships, auto-enrollment
assessments    → Quizzes, assignments, submissions, evaluations
fees           → Fee structures, invoices, payments
schedules      → Timetables, exam schedules, holidays
announcements  → Targeted broadcasts
reports        → Read-only aggregations
it_support     → Tickets, password resets
```

---

## 2. Multi-Role User Design

**Problem:** One person may be both a Teacher and an Admin (small school scenario).

**Solution:** `CustomUser` has a M2M relationship to `Role` via `UserRole` through
table. Permissions are resolved at request time by unioning all active role permissions.

```
CustomUser
    │
    ├── UserRole(role=ADMIN, is_active=True)
    └── UserRole(role=TEACHER, is_active=True)

→ effective permissions = ADMIN permissions ∪ TEACHER permissions
```

Role cache key: `user:{uuid}:roles` in Redis, TTL 15 min.
Invalidated on any `UserRole` create/update.

---

## 3. School ID Generation Design

Every user gets a human-readable `school_id` based on their primary role at creation.

**Format:** `{PREFIX}{zero-padded 3-digit sequence}` e.g. `STD042`, `TCH003`

| Role        | Prefix  |
| ----------- | ------- |
| Student     | `STD` |
| Teacher     | `TCH` |
| Admin       | `ADM` |
| Principal   | `PRI` |
| IT Support  | `IT`  |
| Super Admin | `SA`  |

**Generation algorithm (in `UserService.create_user()`):**

```python
def generate_school_id(primary_role: str) -> str:
    PREFIX_MAP = {
        'STUDENT': 'STD', 'TEACHER': 'TCH', 'ADMIN': 'ADM',
        'PRINCIPAL': 'PRI', 'IT_SUPPORT': 'IT', 'SUPER_ADMIN': 'SA',
    }
    prefix = PREFIX_MAP[primary_role]

    with transaction.atomic():
        # Lock the table for this prefix to prevent race conditions
        last = CustomUser.objects.select_for_update().filter(
            school_id__startswith=prefix
        ).order_by('-school_id').first()

        if last is None:
            next_num = 1
        else:
            # Extract numeric suffix and increment
            current_num = int(last.school_id[len(prefix):])
            next_num = current_num + 1

        return f"{prefix}{next_num:03d}"
```

`school_id` is set once at creation and  **never changes** , even if the user's roles change.

---

## 4. First-Login Password Reset Design

**Problem:** Admin sets an initial password. The user must be forced to change it
before accessing the system, without requiring a separate email flow.

**Flow:**

```
Admin creates user (sets initial password)
    └─→ CustomUser.must_change_password = True
    └─→ school_id generated (e.g. STD042)

User logs in with STD042 + admin-set password
    └─→ Authentication succeeds
    └─→ JWT issued BUT flagged as "restricted"
        JWT payload: { ..., "must_change_password": true }
    └─→ Response: { "force_password_reset": true, "access": "<restricted_jwt>" }

Frontend detects force_password_reset=true
    └─→ Redirects to /reset-password page
    └─→ All other navigation blocked client-side

User submits new password to POST /auth/first-login-reset/
    └─→ RequiresPasswordChange permission: allow (user.must_change_password=True)
    └─→ Validate: min 8 chars, 1 uppercase, 1 digit, ≠ admin-set password
    └─→ Set new password hash
    └─→ Set must_change_password = False
    └─→ Blacklist restricted token
    └─→ Issue fresh unrestricted JWT pair
    └─→ Log FIRST_LOGIN_RESET to AuditLog
    └─→ Response: { "access": "<full_jwt>", "refresh": "<refresh_jwt>" }

Frontend stores new tokens → user proceeds normally
```

**`RequiresPasswordChange` permission class** (enforces the restriction server-side):

```python
class RequiresPasswordChange(BasePermission):
    """
    Applied globally via DEFAULT_PERMISSION_CLASSES or per-view.
    Blocks all endpoints for users who must change their password,
    EXCEPT the first-login-reset endpoint itself.
    """
    EXEMPT_PATHS = [
        '/api/v1/auth/first-login-reset/',
        '/api/v1/auth/logout/',
    ]

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return True  # let IsAuthenticated handle this
        if request.user.must_change_password:
            if request.path in self.EXEMPT_PATHS:
                return True
            return False  # → HTTP 403 with "Password reset required"
        return True
```

**IT Support password reset** re-uses the same mechanism:

* IT Support calls `POST /support/reset-password/` with `user_id` and `new_password`
* Sets `CustomUser.must_change_password = True`
* Next login for that user triggers the same restricted-token → reset flow

No email required. The school_id + new admin/IT-set password is communicated
to the user out-of-band (in person or via a printed slip).

---

## 5. Auto-Enrollment Design

**Trigger points:**

1. Admin assigns a program to a student (`POST /students/{id}/assign-program/`)
2. Admin enrolls student in electives (`POST /students/{id}/enroll-electives/`)

**Signal flow:**

```
StudentProfile.save() [created=True]
    └─→ signal: auto_enroll_core_courses(sender, instance, created)
            └─→ EnrollmentService.enroll_core_courses(student, current_term)
                    └─→ bulk_create Enrollment × 7 core courses
```

**Idempotency:** `Enrollment` has `UNIQUE(student, course, term, level)`.
Use `bulk_create(ignore_conflicts=True)` so re-triggering is safe.

**Current term resolution:**

```python
def get_current_term():
    return Term.objects.select_related('academic_year').get(
        is_current=True
    )  # cached in Redis for 1 hour
```

---

## 6. Term Transition Design

Admin calls `POST /api/v1/terms/transition/`. This runs inside a single DB
transaction with select_for_update to prevent concurrent transitions.

```python
def transition_term(current_term_id):
    with transaction.atomic():
        term = Term.objects.select_for_update().get(id=current_term_id, is_current=True)
        profiles = StudentProfile.objects.select_for_update().filter(status='ACTIVE')

        if term.term_number < 3:
            # Advance term number
            Term.objects.filter(id=term.id).update(is_current=False)
            next_term = Term.objects.get(
                academic_year=term.academic_year,
                term_number=term.term_number + 1
            )
            next_term.is_current = True
            next_term.save()

        elif term.term_number == 3:
            to_graduate = profiles.filter(level__number=3)
            to_promote  = profiles.exclude(level__number=3)

            # Graduate level 3 students
            to_graduate.update(status='GRADUATED')

            # Promote others
            for profile in to_promote:
                profile.level = Level.objects.get(number=profile.level.number + 1)
                profile.save()

            # Reset to new academic year Term 1
            _create_or_set_new_term_1()

        # Mark unpaid fees as overdue
        mark_overdue_fees.delay(term.id)

        # Generate next term fees
        generate_term_fees.delay()
```

---

## 7. Quiz/Assignment Auto-Close Design

Celery Beat runs every 5 minutes:

```python
@shared_task
def close_expired_quizzes():
    now = timezone.now()
    updated = Quiz.objects.filter(
        status='OPEN',
        due_datetime__lte=now
    ).update(status='CLOSED')
    return f"Closed {updated} quizzes"

@shared_task
def close_expired_assignments():
    now = timezone.now()
    updated = Assignment.objects.filter(
        status='OPEN',
        due_datetime__lte=now
    ).update(status='CLOSED')
    return f"Closed {updated} assignments"
```

**DB index** on `(status, due_datetime)` ensures this query is fast even with
thousands of quizzes.

Before any student submission, the view also checks live:

```python
if quiz.due_datetime < timezone.now() or quiz.status != 'OPEN':
    return Response({'message': 'Quiz is closed.'}, status=422)
```

---

## 8. Fee System Design

### Fee Calculation

`StudentFee` is generated by Celery task on term transition:

```python
def calculate_student_fee(student_profile, term):
    base = FeeStructure.objects.filter(
        level=student_profile.level,
        program=student_profile.program,
        is_active=True
    ).aggregate(total=Sum('base_amount'))['total'] or 0

    additional = AdditionalFee.objects.filter(
        term=term, is_active=True
    ).filter(
        Q(applies_to='ALL') |
        Q(applies_to='PROGRAM', program=student_profile.program) |
        Q(applies_to='LEVEL', level=student_profile.level)
    ).aggregate(total=Sum('amount'))['total'] or 0

    StudentFee.objects.update_or_create(
        student=student_profile.user, term=term,
        defaults={
            'base_amount': base,
            'additional_amount': additional,
            'total_amount': base + additional,
        }
    )
```

### Payment Status Computation

Computed in `StudentFee.save()` override — never stored as a static value except
for `OVERDUE` which is set by the transition task:

```python
def save(self, *args, **kwargs):
    if self.payment_status != 'OVERDUE':
        if self.amount_paid == 0:
            self.payment_status = 'NOT_PAID'
        elif self.amount_paid < self.total_amount:
            self.payment_status = 'PARTIALLY_PAID'
        else:
            self.payment_status = 'FULLY_PAID'
    super().save(*args, **kwargs)
```

---

## 9. N+1 Query Prevention

Every ViewSet queryset must be annotated. Examples:

```python
# StudentViewSet
def get_queryset(self):
    return StudentProfile.objects.select_related(
        'user', 'level', 'program'
    ).prefetch_related(
        Prefetch(
            'user__enrollment_set',
            queryset=Enrollment.objects.select_related('course', 'term').filter(is_active=True),
            to_attr='active_enrollments'
        )
    )

# QuizViewSet
def get_queryset(self):
    return Quiz.objects.select_related(
        'assignment__course',
        'assignment__teacher'
    ).prefetch_related(
        'question_set__questionchoice_set'
    )

# AnnouncementViewSet (student sees own)
def get_queryset(self):
    return Announcement.objects.filter(
        announcementrecipient__user=self.request.user
    ).select_related('created_by').annotate(
        is_read=Subquery(
            AnnouncementRecipient.objects.filter(
                announcement=OuterRef('pk'),
                user=self.request.user
            ).values('is_read')[:1]
        )
    )
```

**nplusone** middleware in test settings catches violations automatically:

```python
MIDDLEWARE += ['nplusone.ext.django.NPlusOneMiddleware']
NPLUSONE_RAISE = True  # fail tests on N+1
```

---

## 10. Caching Design

```python
from django.core.cache import cache
from functools import wraps

# View-level cache for static data
@method_decorator(cache_page(60 * 30), name='list')  # 30 min for course list
class CourseViewSet(ModelViewSet): ...

# Object-level cache
def get_fee_structure(level_id, program_id):
    key = f'fee_structure:{level_id}:{program_id}'
    result = cache.get(key)
    if result is None:
        result = FeeStructure.objects.filter(
            level_id=level_id, program_id=program_id, is_active=True
        ).aggregate(total=Sum('base_amount'))
        cache.set(key, result, 3600)
    return result

# Cache invalidation on update
class FeeStructureViewSet(ModelViewSet):
    def perform_update(self, serializer):
        instance = serializer.save()
        cache.delete(f'fee_structure:{instance.level_id}:{instance.program_id}')
```

---

## 11. File Upload Design

```
Student submits assignment
    └─→ DRF view receives multipart request
    └─→ FileValidator: check MIME with python-magic
    └─→ MaxFileSizeValidator: 50MB
    └─→ django-storages uploads to S3: sms-submissions/{school_id}/{uuid}.pdf
    └─→ AssignmentSubmission.file = S3 key (not public URL)
    └─→ On read: generate_presigned_url(key, expires=3600)
```

Teacher resource upload: `sms-resources/{course_id}/{uuid}.{ext}`

**Never store full S3 URLs** in the DB — store the key only and generate
pre-signed URLs at read time so bucket stays private.

---

## 12. Report Generation Design

Reports run as Celery tasks to avoid blocking the request:

```
Admin requests report
    └─→ POST /api/v1/reports/export/ → returns { task_id }
    └─→ Celery task: query DB (read replica if configured)
    └─→ Stream rows into CSV via csv.writer
    └─→ Upload CSV to S3: sms-reports/{task_id}.csv
    └─→ Update ReportTask.status = DONE, download_url = presigned URL (24h)
    └─→ Admin polls GET /api/v1/reports/export/{task_id}/
```

---

## 13. Testing Strategy

### Test Pyramid

```
                ┌──────────┐
                │   E2E    │  ← few, smoke only
                │  (2–5)   │
              ┌─┴──────────┴─┐
              │ Integration  │  ← API-level, real DB
              │  (100–200)   │
            ┌─┴──────────────┴─┐
            │   Unit Tests     │  ← services, models, signals
            │   (300–500+)     │
            └──────────────────┘
```

### Unit Tests (pytest-django)

* Services: `EnrollmentService`, `TermTransitionService`, `FeeCalculationService`
* Model methods: `StudentFee.save()` status logic, `CustomUser.has_role()`
* Signal handlers: auto-enrollment fires correctly, idempotent
* Serializer validation: 4-elective constraint, attempt limit

### Integration Tests

* Full enrollment flow: create student → assign program → assert 7 core enrollments
* Term transition: assert level promotion, graduation, overdue fees
* Quiz lifecycle: create → publish → attempt → submit → auto-close
* Fee payment: record payment → assert status change → overdue on transition
* Permission matrix: each role on each endpoint (use parametrize)

### Test Factories

```python
# tests/factories/__init__.py
class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser
    school_id = factory.Sequence(lambda n: f"STD{n:03d}")
    email = factory.Sequence(lambda n: f"user{n}@school.gh")
    first_name = factory.Faker('first_name')
    must_change_password = False   # default False in tests; set True explicitly when testing first-login flow

class StudentProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = StudentProfile
    user = factory.SubFactory(UserFactory)
    level = factory.SubFactory(LevelFactory, number=1)
    status = 'ACTIVE'
```

### Test Settings

```python
# config/settings/test.py
CELERY_TASK_ALWAYS_EAGER = True      # run tasks synchronously
CELERY_TASK_EAGER_PROPAGATES = True  # raise exceptions in tests
CACHES = { 'default': { 'BACKEND': 'django.core.cache.backends.locmem.LocMemCache' } }
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'
NPLUSONE_RAISE = True                # fail on N+1 queries
```

### Coverage Target

```
apps/users/        ≥ 90%
apps/academics/    ≥ 85%
apps/enrollment/   ≥ 90%  ← critical path
apps/assessments/  ≥ 85%
apps/fees/         ≥ 90%  ← financial data
apps/schedules/    ≥ 75%
apps/announcements/≥ 80%
apps/reports/      ≥ 75%
apps/it_support/   ≥ 80%
Overall target:    ≥ 85%
```

---

## 14. Performance Benchmarks (targets)

| Endpoint                         | Target P95 | Notes                      |
| -------------------------------- | ---------- | -------------------------- |
| `POST /auth/login/`            | < 200ms    | JWT generation + DB lookup |
| `GET /students/`               | < 150ms    | Paginated, cached          |
| `GET /student/{id}/courses/`   | < 100ms    | select_related optimized   |
| `POST /terms/transition/`      | < 2s       | Bulk updates, async fees   |
| `GET /reports/fee-collection/` | < 500ms    | Aggregation query          |
| `POST /export/`                | < 100ms    | Async, returns task_id     |
| File upload                      | < 5s       | 50MB to S3                 |
