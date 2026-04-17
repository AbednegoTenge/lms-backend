# Permissions Matrix — School Management System

## Roles

| Code            | Role          | Created By          |
| --------------- | ------------- | ------------------- |
| `SUPER_ADMIN` | Super Admin   | System / env seed   |
| `ADMIN`       | Administrator | Super Admin         |
| `PRINCIPAL`   | Principal     | Admin / Super Admin |
| `TEACHER`     | Teacher       | Admin / Super Admin |
| `STUDENT`     | Student       | Admin / Super Admin |
| `IT_SUPPORT`  | IT Support    | Super Admin ONLY    |

**Multi-role rule:** A user may hold multiple roles simultaneously.
Effective permission is the **union** of all assigned roles. Evaluated in
`RolePermission.has_permission()` by checking `request.user.roles` (cached).

---

## Implementation Pattern

```python
# apps/users/permissions.py

class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return request.user.has_role('ADMIN')

class IsTeacher(BasePermission):
    def has_permission(self, request, view):
        return request.user.has_role('TEACHER')

class IsStudent(BasePermission):
    def has_permission(self, request, view):
        return request.user.has_role('STUDENT')

class IsAdminOrPrincipal(BasePermission):
    def has_permission(self, request, view):
        return request.user.has_any_role(['ADMIN', 'PRINCIPAL'])

# CustomUser method (cached via Redis):
def has_role(self, role_name):
    return role_name in self.get_cached_roles()

def has_any_role(self, role_names):
    return bool(set(role_names) & set(self.get_cached_roles()))

def get_cached_roles(self):
    key = f'user:{self.id}:roles'
    roles = cache.get(key)
    if roles is None:
        roles = list(self.userrole_set.filter(
            is_active=True
        ).values_list('role__name', flat=True))
        cache.set(key, roles, timeout=900)  # 15 min
    return roles
```

---

## Permissions Matrix

### User Management

| Action             | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ------------------ | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Create Admin       |     ✓     |  ✗  |    ✗    |   ✗   |   ✗   |     ✗     |
| Create IT Support  |     ✓     |  ✗  |    ✗    |   ✗   |   ✗   |     ✗     |
| Create Principal   |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Create Teacher     |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Create Student     |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Update any user    |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Update own profile |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✓     |
| Deactivate user    |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| View all users     |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✓     |
| Reset any password |     ✓     |  ✗  |    ✗    |   ✗   |   ✗   |     ✓     |
| Reset own password |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✓     |

### Academic Management

| Action                    | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ------------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| CRUD Academic Year        |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| CRUD Term                 |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Trigger term transition   |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| CRUD Program              |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| CRUD Course               |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| View courses              |     ✓     |  ✓  |    ✓    |   ✓   |   ✓*   |     ✗     |
| Assign student to program |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Assign teacher to course  |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Assign student to class   |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |

*Student sees only enrolled courses.

### Enrollment

| Action                      | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| --------------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Enroll student in electives |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| View own enrollment         |      -      |   -   |     -     |    -    |   ✓   |     ✗     |
| View student enrollment     |     ✓     |  ✓  |    ✓    |   ✓*   |   ✗   |     ✗     |
| Remove enrollment           |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |

*Teacher sees only students enrolled in their assigned course.

### Assessments — Quiz

| Action                   | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ------------------------ | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Create quiz              |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Edit quiz (DRAFT only)   |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Publish quiz (→ OPEN)   |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Delete quiz (DRAFT only) |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| View quiz                |     ✓     |  ✓  |    ✓    |   ✓*   |  ✓**  |     ✗     |
| Attempt quiz             |     ✗     |  ✗  |    ✗    |   ✗   |  ✓**  |     ✗     |
| View all submissions     |     ✓     |  ✓  |    ✓    |   ✓*   |   ✗   |     ✗     |
| View own submission      |     ✗     |  ✗  |    ✗    |   ✗   |  ✓**  |     ✗     |

*Teacher: only for courses they are assigned to.
**Student: only for courses they are enrolled in, and only when quiz is OPEN.

### Assessments — Assignment

| Action                  | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ----------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Create assignment       |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Edit assignment (DRAFT) |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Grade submission        |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Submit assignment       |     ✗     |  ✗  |    ✗    |   ✗   |  ✓**  |     ✗     |
| View own submission     |     ✗     |  ✗  |    ✗    |   ✗   |  ✓**  |     ✗     |
| View all submissions    |     ✓     |  ✓  |    ✓    |   ✓*   |   ✗   |     ✗     |

### Resources & Course Outline

| Action                     | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| -------------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Upload resource            |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| Delete resource            |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| View resources             |     ✓     |  ✓  |    ✓    |   ✓*   |  ✓**  |     ✗     |
| Create/edit course outline |     ✓     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |
| View course outline        |     ✓     |  ✓  |    ✓    |   ✓*   |  ✓**  |     ✗     |

### Teacher Evaluation

| Action                        | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ----------------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Submit evaluation             |     ✗     |  ✗  |    ✗    |   ✗   |  ✓**  |     ✗     |
| View all evaluations          |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✗     |
| View own evaluations received |     ✗     |  ✗  |    ✗    |   ✓*   |   ✗   |     ✗     |

### Fees

| Action                 | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ---------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| CRUD Fee Structure     |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Generate term invoices |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| Record payment         |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| View all student fees  |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✗     |
| View own fee           |     ✗     |  ✗  |    ✗    |   ✗   |   ✓   |     ✗     |
| Send fee reminder      |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |

### Schedules

| Action                  | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ----------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| CRUD Timetable          |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| CRUD Exam Schedule      |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| CRUD Holidays/Vacations |     ✓     |  ✓  |    ✗    |   ✗   |   ✗   |     ✗     |
| View schedules          |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✗     |

### Announcements

| Action                   | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| ------------------------ | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Create announcement      |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✓     |
| Edit own announcement    |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✓     |
| Delete own announcement  |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✓     |
| View announcements (own) |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✓     |
| Mark announcement read   |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✓     |

### Reports

| Action                      | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| --------------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Academic performance report |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✗     |
| Fee collection report       |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✗     |
| Teacher evaluation report   |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✗     |
| Own progress report         |     ✗     |  ✗  |    ✗    |   ✗   |   ✓   |     ✗     |
| Export report (CSV/PDF)     |     ✓     |  ✓  |    ✓    |   ✗   |   ✗   |     ✗     |

### IT Support

| Action                | Super Admin | Admin | Principal | Teacher | Student | IT Support |
| --------------------- | :---------: | :---: | :-------: | :-----: | :-----: | :--------: |
| Create support ticket |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✓     |
| Assign/resolve ticket |     ✓     |  ✗  |    ✗    |   ✗   |   ✗   |     ✓     |
| View all tickets      |     ✓     |  ✗  |    ✗    |   ✗   |   ✗   |     ✓     |
| View own ticket       |     ✓     |  ✓  |    ✓    |   ✓   |   ✓   |     ✓     |
| Reset user password   |     ✓     |  ✗  |    ✗    |   ✗   |   ✗   |     ✓     |

---

## Object-Level Permission Rules

These are enforced via `has_object_permission()`:

| Object                                   | Rule                                                                      |
| ---------------------------------------- | ------------------------------------------------------------------------- |
| `Quiz`/`Assignment`                  | Teacher can only edit if assigned to that course this term                |
| `QuizAttempt`/`AssignmentSubmission` | Student can only access own submission                                    |
| `Enrollment`                           | Teacher can only view enrollments for courses assigned to them            |
| `TeacherEvaluation`                    | Student can only view/edit own evaluation; teacher reads but can't modify |
| `SupportTicket`                        | User can only view own ticket unless IT Support                           |
| `Announcement`                         | User can only see announcements addressed to them                         |

---

## Throttle Classes by Endpoint Group

```python
class AuthThrottle(UserRateThrottle):
    rate = '5/min'

class UploadThrottle(UserRateThrottle):
    rate = '10/hour'

class ReportThrottle(UserRateThrottle):
    rate = '20/hour'
```
