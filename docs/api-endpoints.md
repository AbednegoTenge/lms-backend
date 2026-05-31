# API Endpoint Index

Source-scanned endpoint list grouped by Django app.

## Base URLs

| Area | Prefix |
| --- | --- |
| Auth | `/api/v1/auth/` |
| All other apps | `/api/v1/` |

## users

| Method | Endpoint |
| --- | --- |
| POST | `/api/v1/auth/login/` |
| POST | `/api/v1/auth/refresh/` |
| POST | `/api/v1/auth/logout/` |
| POST | `/api/v1/auth/first-login-reset/` |

## academics

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/academic-years/` |
| GET, PUT, PATCH, DELETE | `/api/v1/academic-years/{id}/` |
| GET, POST | `/api/v1/terms/` |
| GET, PUT, PATCH, DELETE | `/api/v1/terms/{id}/` |
| POST | `/api/v1/terms/transition/` |
| GET | `/api/v1/levels/` |
| GET | `/api/v1/levels/{id}/` |
| GET | `/api/v1/programs/` |
| GET | `/api/v1/programs/{id}/` |
| GET, POST | `/api/v1/courses/` |
| GET, PUT, PATCH, DELETE | `/api/v1/courses/{id}/` |
| POST | `/api/v1/courses/{id}/assign-teacher/` |
| GET, POST | `/api/v1/assignments/` |
| GET, PUT, PATCH, DELETE | `/api/v1/assignments/{id}/` |
| GET, PUT | `/api/v1/assignments/{assignment_id}/outline/` |

## enrollment

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/students/` |
| GET, PATCH, DELETE | `/api/v1/students/{id}/` |
| POST | `/api/v1/students/{id}/assign-program/` |
| POST | `/api/v1/students/{id}/enroll-electives/` |
| GET | `/api/v1/students/{id}/courses/` |
| GET | `/api/v1/students/{id}/fees/` |

## assessments

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/assignments/{assignment_id}/resources/` |
| DELETE | `/api/v1/assignments/{assignment_id}/resources/{id}/` |
| GET, POST | `/api/v1/quizzes/` |
| GET, PATCH | `/api/v1/quizzes/{id}/` |
| POST | `/api/v1/quizzes/{id}/publish/` |
| POST | `/api/v1/quizzes/{id}/attempts/` |
| GET | `/api/v1/quizzes/{id}/submissions/` |
| POST | `/api/v1/quiz-attempts/{id}/submit/` |
| GET, POST | `/api/v1/course-assignments/` |
| GET, PATCH | `/api/v1/course-assignments/{id}/` |
| POST | `/api/v1/course-assignments/{id}/publish/` |
| POST | `/api/v1/course-assignments/{id}/submit/` |
| GET | `/api/v1/course-assignments/{id}/submissions/` |
| PATCH | `/api/v1/assignment-submissions/{id}/grade/` |
| GET, POST | `/api/v1/evaluations/` |

## fees

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/fee-structures/` |
| PATCH, DELETE | `/api/v1/fee-structures/{id}/` |
| GET | `/api/v1/student-fees/` |
| POST | `/api/v1/student-fees/send-reminder/` |
| GET | `/api/v1/student-fees/{id}/` |
| POST | `/api/v1/student-fees/{id}/payments/` |

## schedules

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/timetables/` |
| GET, PATCH, DELETE | `/api/v1/timetables/{id}/` |
| GET, POST | `/api/v1/exam-schedules/` |
| GET, PATCH, DELETE | `/api/v1/exam-schedules/{id}/` |
| GET, POST | `/api/v1/holidays/` |
| GET, PATCH, DELETE | `/api/v1/holidays/{id}/` |

## announcements

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/announcements/` |
| GET, PATCH, DELETE | `/api/v1/announcements/{id}/` |
| POST | `/api/v1/announcements/{id}/publish/` |
| POST | `/api/v1/announcements/{id}/read/` |

## reports

| Method | Endpoint |
| --- | --- |
| GET | `/api/v1/reports/academic-performance/` |
| GET | `/api/v1/reports/fee-collection/` |
| GET | `/api/v1/reports/teacher-evaluations/` |
| POST | `/api/v1/reports/export/` |
| GET | `/api/v1/reports/export/{id}/` |

## it_support

| Method | Endpoint |
| --- | --- |
| GET, POST | `/api/v1/support-tickets/` |
| GET, PATCH | `/api/v1/support-tickets/{id}/` |
| POST | `/api/v1/support/reset-password/` |

