# Data Models — School Management System

All models use  **UUID primary keys** . All timestamps are UTC.
Soft-delete via `is_active` or `status` field — never hard delete student/teacher records.

---

## `users` App

### `CustomUser`

```python
id                  UUID PK
school_id           CharField(20) UNIQUE NOT NULL   # e.g. STD001, TCH003, ADM001, PRI001, IT002
email               EmailField UNIQUE NOT NULL
first_name          CharField(100)
last_name           CharField(100)
phone               CharField(20) nullable
is_active           BooleanField default=True
is_staff            BooleanField default=False      # Django admin access
must_change_password BooleanField default=True      # True on creation; set False after first-login reset
date_joined         DateTimeField auto_now_add
last_login          DateTimeField nullable
profile_photo       ImageField nullable (S3)
```

**Login identifier:** `school_id` (not email). Users log in with their school ID
and the password set by the admin at creation.

**`school_id` format and generation rules:**

| Role        | Prefix  | Example               |
| ----------- | ------- | --------------------- |
| Student     | `STD` | `STD001`,`STD042` |
| Teacher     | `TCH` | `TCH001`,`TCH015` |
| Admin       | `ADM` | `ADM001`            |
| Principal   | `PRI` | `PRI001`            |
| IT Support  | `IT`  | `IT001`,`IT003`   |
| Super Admin | `SA`  | `SA001`             |

`school_id` is auto-generated in `UserService.create_user()` by:

1. Determining the primary role being assigned
2. Querying `MAX(school_id)` for that prefix and incrementing
3. Zero-padding to 3 digits (e.g. `STD` + `007`)
4. Generation is inside a `select_for_update` transaction to prevent race conditions

If a user holds multiple roles, `school_id` is based on the **first/primary role** assigned at creation. Secondary roles do not change the ID.

**`must_change_password` flow:**

* Set to `True` by default on all new accounts
* The admin sets the initial password during user creation
* On login, if `must_change_password == True`, the API returns HTTP 200 with
  `"force_password_reset": true` — the frontend must redirect to the reset page
* After the user successfully sets a new password, `must_change_password` is set to `False`
* Subsequent logins proceed normally

### `Role`

```python
id      UUID PK
name    CharField CHOICES: [STUDENT, TEACHER, ADMIN, PRINCIPAL, IT_SUPPORT, SUPER_ADMIN]
```

Seeded once via migration. Never created at runtime.

### `UserRole`

```python
id          UUID PK
user        FK → CustomUser
role        FK → Role
assigned_by FK → CustomUser nullable  # who granted this role
assigned_at DateTimeField auto_now_add
is_active   BooleanField default=True
```

`UNIQUE(user, role)`. A user can hold multiple roles.

### `AuditLog`

```python
id          UUID PK
user        FK → CustomUser nullable (null = system action)
action      CharField(50)   # CREATE, UPDATE, DELETE, LOGIN, RESET_PASSWORD, FIRST_LOGIN_RESET
model_name  CharField(100)
object_id   UUIDField
diff        JSONField        # {field: [old_val, new_val]}
ip_address  GenericIPAddressField nullable
timestamp   DateTimeField auto_now_add
```

Write-only. Never updated. Index on `(user_id, timestamp DESC)`.

---

## `academics` App

### `AcademicYear`

```python
id          UUID PK
name        CharField(20)   # e.g. "2024/2025"
start_date  DateField
end_date    DateField
is_current  BooleanField default=False
created_by  FK → CustomUser
```

Only one `is_current=True` at a time (enforced via `save()` override).

### `Term`

```python
id              UUID PK
academic_year   FK → AcademicYear
term_number     IntegerField CHOICES: [1, 2, 3]
start_date      DateField
end_date        DateField
is_current      BooleanField default=False
```

`UNIQUE(academic_year, term_number)`.

### `Level`

```python
id      UUID PK
number  IntegerField CHOICES: [1, 2, 3]
name    CharField(20)   # e.g. "Level 1 / Form 1"
```

Seeded. Never created at runtime.

### `Program`

```python
id      UUID PK
name    CharField CHOICES:
          [GENERAL_ARTS, GENERAL_SCIENCE, HOME_ECONOMICS, BUSINESS, VISUAL_ARTS]
code    CharField(10) UNIQUE   # e.g. "GA", "GS"
```

Seeded. Never created at runtime.

### `Course`

```python
id          UUID PK
name        CharField(200)
code        CharField(20) UNIQUE
course_type CharField CHOICES: [CORE, ELECTIVE]
program     FK → Program nullable   # null for CORE courses
is_active   BooleanField default=True
```

Core courses: `program=NULL, course_type=CORE`.
Elective courses: `program=FK, course_type=ELECTIVE`.

### `TeacherCourseAssignment`

```python
id          UUID PK
teacher     FK → CustomUser (role=TEACHER)
course      FK → Course
term        FK → Term
level       FK → Level
is_active   BooleanField default=True
assigned_by FK → CustomUser (role=ADMIN)
assigned_at DateTimeField auto_now_add
```

`UNIQUE(teacher, course, term, level)`.

### `CourseOutline`

```python
id          UUID PK
assignment  FK → TeacherCourseAssignment
created_at  DateTimeField auto_now_add
updated_at  DateTimeField auto_now
```

### `WeeklyTopic`

```python
id          UUID PK
outline     FK → CourseOutline
week_number IntegerField   # 1–14
title       CharField(200)
description TextField
```

`UNIQUE(outline, week_number)`.

---

## `enrollment` App

### `StudentProfile`

```python
id              UUID PK  (same UUID as CustomUser)
user            OneToOneField → CustomUser
level           FK → Level
program         FK → Program nullable   # set when admin assigns program
class_section   CharField(10) nullable  # e.g. "1A", "2B"
status          CharField CHOICES: [ACTIVE, INACTIVE, GRADUATED, SUSPENDED]
enrolled_date   DateField
```

Note: The student's human-readable ID is `CustomUser.school_id` (e.g. `STD001`).
`StudentProfile` does not store a separate ID field.

### `Enrollment`

```python
id          UUID PK
student     FK → CustomUser
course      FK → Course
term        FK → Term
level       FK → Level
enrollment_type  CharField CHOICES: [CORE, ELECTIVE]
enrolled_at DateTimeField auto_now_add
enrolled_by FK → CustomUser nullable   # null = auto (signal)
is_active   BooleanField default=True
```

`UNIQUE(student, course, term, level)`.

Constraint: count of `ELECTIVE` enrollments per `(student, term)` must be
exactly 4. Validated in serializer and enforced in service layer.

---

## `assessments` App

### `Resource`

```python
id              UUID PK
assignment      FK → TeacherCourseAssignment
title           CharField(200)
resource_type   CharField CHOICES: [VIDEO_LINK, PDF, PRESENTATION, OTHER]
url             URLField nullable    # for VIDEO_LINK
file            FileField nullable   # S3 for PDF/PRESENTATION
uploaded_at     DateTimeField auto_now_add
```

### `Quiz`

```python
id              UUID PK
assignment      FK → TeacherCourseAssignment
title           CharField(200)
instructions    TextField nullable
max_attempts    PositiveIntegerField default=1
due_datetime    DateTimeField
status          CharField CHOICES: [DRAFT, OPEN, CLOSED] default=DRAFT
total_marks     DecimalField(6,2)
created_at      DateTimeField auto_now_add
updated_at      DateTimeField auto_now
```

Status auto-transitions to `CLOSED` via Celery Beat when `due_datetime` passes.

### `Question`

```python
id              UUID PK
quiz            FK → Quiz
question_text   TextField
question_type   CharField CHOICES:
                  [MULTIPLE_CHOICE, MULTIPLE_ANSWER, TRUE_FALSE, SHORT_ANSWER]
marks           DecimalField(5,2)
order           PositiveIntegerField
```

### `QuestionChoice`

```python
id          UUID PK
question    FK → Question (only for MULTIPLE_CHOICE, MULTIPLE_ANSWER, TRUE_FALSE)
text        CharField(500)
is_correct  BooleanField
```

### `QuizAttempt`

```python
id              UUID PK
quiz            FK → Quiz
student         FK → CustomUser
attempt_number  PositiveIntegerField
started_at      DateTimeField auto_now_add
submitted_at    DateTimeField nullable
score           DecimalField(6,2) nullable
status          CharField CHOICES: [IN_PROGRESS, SUBMITTED, GRADED]
```

`UNIQUE(quiz, student, attempt_number)`.
Before insert: validate `attempt_number <= quiz.max_attempts` and `quiz.status == OPEN`.

### `QuizAnswer`

```python
id          UUID PK
attempt     FK → QuizAttempt
question    FK → Question
# For MC/TF: store selected choice(s)
choices     ManyToManyField → QuestionChoice (blank=True)
# For SHORT_ANSWER:
text_answer TextField nullable
```

### `Assignment`

```python
id              UUID PK
assignment      FK → TeacherCourseAssignment
title           CharField(200)
description     TextField
due_datetime    DateTimeField
submission_type CharField CHOICES: [DOCUMENT, TEXT, BOTH] default=BOTH
max_marks       DecimalField(6,2)
status          CharField CHOICES: [DRAFT, OPEN, CLOSED] default=DRAFT
created_at      DateTimeField auto_now_add
```

### `AssignmentSubmission`

```python
id              UUID PK
assignment      FK → Assignment
student         FK → CustomUser
submitted_at    DateTimeField auto_now_add
text_content    TextField nullable
file            FileField nullable (S3)
marks_obtained  DecimalField(6,2) nullable
feedback        TextField nullable
graded_by       FK → CustomUser nullable
graded_at       DateTimeField nullable
status          CharField CHOICES: [SUBMITTED, GRADED, LATE]
```

Before insert: validate `assignment.status == OPEN`.

### `TeacherEvaluation`

```python
id              UUID PK
student         FK → CustomUser
teacher         FK → CustomUser
course          FK → Course
term            FK → Term
rating          PositiveSmallIntegerField   # 1–5
comment         TextField nullable
submitted_at    DateTimeField auto_now_add
```

`UNIQUE(student, teacher, course, term)` — one evaluation per combo.

---

## `fees` App

### `FeeStructure`

```python
id          UUID PK
level       FK → Level
program     FK → Program nullable   # null = applies to all programs
term        FK → Term nullable      # null = applies every term
base_amount DecimalField(12,2)
description CharField(200)
effective_from DateField
is_active   BooleanField default=True
created_by  FK → CustomUser
```

### `AdditionalFee`

```python
id              UUID PK
name            CharField(200)   # e.g. "Lab Materials", "Sports Levy"
amount          DecimalField(12,2)
applies_to      CharField CHOICES: [ALL, PROGRAM, LEVEL]
program         FK → Program nullable
level           FK → Level nullable
term            FK → Term
is_active       BooleanField default=True
```

### `StudentFee`

```python
id              UUID PK
student         FK → CustomUser
term            FK → Term
base_amount     DecimalField(12,2)
additional_amount DecimalField(12,2) default=0
total_amount    DecimalField(12,2)  # computed: base + additional
amount_paid     DecimalField(12,2) default=0
payment_status  CharField CHOICES: [NOT_PAID, PARTIALLY_PAID, FULLY_PAID, OVERDUE]
                default=NOT_PAID
generated_at    DateTimeField auto_now_add
updated_at      DateTimeField auto_now
```

`UNIQUE(student, term)`.
`payment_status` is computed via `save()` override:

* `amount_paid == 0` → NOT_PAID
* `0 < amount_paid < total_amount` → PARTIALLY_PAID
* `amount_paid >= total_amount` → FULLY_PAID
* Carried forward from prior term unpaid → OVERDUE

### `Payment`

```python
id              UUID PK
student_fee     FK → StudentFee
amount          DecimalField(12,2)
payment_method  CharField CHOICES: [CASH, BANK_TRANSFER, MOBILE_MONEY, OTHER]
reference       CharField(100) nullable  # bank/mobile ref
recorded_by     FK → CustomUser  # admin who recorded
paid_at         DateTimeField
notes           TextField nullable
```

---

## `schedules` App

### `ClassTimetable`

```python
id          UUID PK
course      FK → Course
teacher     FK → CustomUser
level       FK → Level
class_section CharField(10)
term        FK → Term
day_of_week IntegerField CHOICES: [0=Mon .. 4=Fri]
start_time  TimeField
end_time    TimeField
room        CharField(50)
```

### `ExamSchedule`

```python
id          UUID PK
course      FK → Course
level       FK → Level
term        FK → Term
exam_date   DateField
start_time  TimeField
end_time    TimeField
room        CharField(50)
exam_type   CharField CHOICES: [MID_TERM, END_OF_TERM]
```

### `Holiday`

```python
id          UUID PK
name        CharField(200)
start_date  DateField
end_date    DateField
academic_year FK → AcademicYear
```

---

## `announcements` App

### `Announcement`

```python
id              UUID PK
title           CharField(300)
body            TextField
created_by      FK → CustomUser
recipient_type  CharField CHOICES:
                  [ALL, ALL_STUDENTS, ALL_TEACHERS, BY_PROGRAM,
                   BY_LEVEL, PRINCIPAL, SPECIFIC_USERS]
program         FK → Program nullable   # if BY_PROGRAM
level           FK → Level nullable     # if BY_LEVEL
created_at      DateTimeField auto_now_add
is_published    BooleanField default=False
published_at    DateTimeField nullable
```

### `AnnouncementRecipient`

```python
id              UUID PK
announcement    FK → Announcement
user            FK → CustomUser
is_read         BooleanField default=False
read_at         DateTimeField nullable
```

Populated by Celery task on publish. Index on `(user_id, announcement_id)`.

---

## `it_support` App

### `SupportTicket`

```python
id              UUID PK
raised_by       FK → CustomUser
assigned_to     FK → CustomUser nullable  # IT Support user
title           CharField(300)
description     TextField
category        CharField CHOICES: [PASSWORD_RESET, COURSE_ISSUE, SYSTEM_BUG, OTHER]
status          CharField CHOICES: [OPEN, IN_PROGRESS, RESOLVED, CLOSED]
priority        CharField CHOICES: [LOW, MEDIUM, HIGH, CRITICAL]
created_at      DateTimeField auto_now_add
updated_at      DateTimeField auto_now
resolved_at     DateTimeField nullable
```

### `PasswordResetRequest`

```python
id              UUID PK
requested_for   FK → CustomUser
reset_by        FK → CustomUser  # IT Support
new_password_hash CharField   # bcrypt hash
reset_at        DateTimeField auto_now_add
reason          TextField nullable
```

---

## Signal Map

| Signal        | Sender                              | Receiver                  | Effect                                                    |
| ------------- | ----------------------------------- | ------------------------- | --------------------------------------------------------- |
| `post_save` | `StudentProfile`(created)         | `enrollment.signals`    | Auto-enroll in all 7 core courses for current term        |
| `post_save` | `Enrollment`(ELECTIVE, count=4)   | `enrollment.signals`    | Trigger core course enrollment if not already enrolled    |
| `post_save` | `StudentFee`(saved)               | `fees.signals`          | Recompute `payment_status`                              |
| `post_save` | `Payment`(created)                | `fees.signals`          | Update `StudentFee.amount_paid`, recompute status       |
| `post_save` | `Announcement`(is_published=True) | `announcements.signals` | Enqueue Celery task to populate `AnnouncementRecipient` |
