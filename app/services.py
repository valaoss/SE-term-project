import os
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator

from google.auth.transport import requests
from google.oauth2 import id_token


class AuthError(ValueError):
    pass


class CourseAccessError(ValueError):
    pass


class CourseNotFoundError(CourseAccessError):
    pass


class ActivityNotFoundError(ValueError):
    pass


class DatabaseConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstructorUser:
    email: str
    name: str | None = None
    google_sub: str | None = None


@dataclass(frozen=True)
class StudentUser:
    email: str
    name: str | None = None
    google_sub: str | None = None


def _allowed_instructor_emails() -> set[str]:
    raw = os.getenv("INSTRUCTOR_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def _allowed_student_emails() -> set[str]:
    raw = os.getenv("STUDENT_EMAILS", "")
    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def _demo_course_id() -> str:
    return os.getenv("DEMO_COURSE_ID", "se101").strip() or "se101"


def _demo_course_name() -> str:
    return os.getenv("DEMO_COURSE_NAME", "Software Engineering").strip() or "Software Engineering"


def _demo_instructor_emails() -> set[str]:
    raw = os.getenv("DEMO_INSTRUCTOR_EMAILS", "")
    explicit_emails = {
        email.strip().lower() for email in raw.split(",") if email.strip()
    }
    emails = explicit_emails or _allowed_instructor_emails()
    if os.getenv("DEV_MODE", "").strip().lower() == "true":
        emails.add(
            os.getenv("DEV_INSTRUCTOR_EMAIL", "dev-instructor@example.com")
            .strip()
            .lower()
        )

    return emails


def _demo_student_emails() -> set[str]:
    raw = os.getenv("DEMO_STUDENT_EMAILS", "")
    explicit_emails = {
        email.strip().lower() for email in raw.split(",") if email.strip()
    }
    return explicit_emails or _allowed_student_emails()


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise DatabaseConfigError("DATABASE_URL is not configured")

    return database_url


def _dev_mode_enabled() -> bool:
    return os.getenv("DEV_MODE", "").strip().lower() == "true"


def _use_memory_activity_store() -> bool:
    return _dev_mode_enabled() and not (
        os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    )


_memory_activities: dict[str, list[dict[str, Any]]] = {}


def _memory_course_id(course_id: str) -> str:
    normalized_course_id = course_id.strip().lower()
    if not normalized_course_id:
        raise CourseAccessError("Course id is required")
    if normalized_course_id != _demo_course_id().lower():
        raise CourseNotFoundError("Course was not found")

    return _demo_course_id()


def _seed_memory_activity_data() -> None:
    course_id = _demo_course_id()
    if course_id in _memory_activities:
        return

    _memory_activities[course_id] = [
        {
            "course_id": course_id,
            "activity_no": 1,
            "title": "Project proposal",
            "status": "NOT_STARTED",
        },
        {
            "course_id": course_id,
            "activity_no": 2,
            "title": "Requirements analysis",
            "status": "ACTIVE",
        },
        {
            "course_id": course_id,
            "activity_no": 3,
            "title": "Sprint planning",
            "status": "ENDED",
        },
    ]


def _connect_to_postgres() -> Any:
    database_url = _database_url()
    try:
        import psycopg

        return psycopg.connect(database_url)
    except ModuleNotFoundError:
        try:
            import psycopg2

            return psycopg2.connect(database_url)
        except ModuleNotFoundError as exc:
            raise DatabaseConfigError("Install psycopg or psycopg2 to use PostgreSQL") from exc


@contextmanager
def _db_connection() -> Iterator[Any]:
    connection = _connect_to_postgres()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _row_to_dict(row: Any, columns: list[str]) -> dict[str, Any]:
    if isinstance(row, dict):
        return row

    if hasattr(row, "keys"):
        return {column: row[column] for column in row.keys()}

    return dict(zip(columns, row))


def _fetch_one_as_dict(cursor: Any) -> dict[str, Any] | None:
    row = cursor.fetchone()
    if row is None:
        return None

    columns = [column[0] for column in cursor.description]
    return _row_to_dict(row, columns)


def _fetch_all_as_dicts(cursor: Any) -> list[dict[str, Any]]:
    rows = cursor.fetchall()
    columns = [column[0] for column in cursor.description]
    return [_row_to_dict(row, columns) for row in rows]


def initialize_activity_schema() -> None:
    if _use_memory_activity_store():
        return

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS courses (
                    course_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS instructor_courses (
                    instructor_email TEXT NOT NULL,
                    course_id TEXT NOT NULL REFERENCES courses(course_id)
                        ON DELETE CASCADE,
                    PRIMARY KEY (instructor_email, course_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS student_courses (
                    student_email TEXT NOT NULL,
                    course_id TEXT NOT NULL REFERENCES courses(course_id)
                        ON DELETE CASCADE,
                    PRIMARY KEY (student_email, course_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    activity_id BIGSERIAL PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(course_id)
                        ON DELETE CASCADE,
                    activity_no INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('NOT_STARTED', 'ACTIVE', 'ENDED')
                    ),
                    UNIQUE (course_id, activity_no)
                )
                """
            )


def seed_demo_activity_data() -> None:
    if _use_memory_activity_store():
        _seed_memory_activity_data()
        return

    course_id = _demo_course_id()
    course_name = _demo_course_name()
    activities = (
        (1, "Project proposal", "NOT_STARTED"),
        (2, "Requirements analysis", "ACTIVE"),
        (3, "Sprint planning", "ENDED"),
    )

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO courses (course_id, name)
                VALUES (%s, %s)
                ON CONFLICT (course_id) DO UPDATE
                SET name = EXCLUDED.name
                """,
                (course_id, course_name),
            )
            for instructor_email in _demo_instructor_emails():
                cursor.execute(
                    """
                    INSERT INTO instructor_courses (instructor_email, course_id)
                    VALUES (%s, %s)
                    ON CONFLICT (instructor_email, course_id) DO NOTHING
                    """,
                    (instructor_email, course_id),
                )
            for student_email in _demo_student_emails():
                cursor.execute(
                    """
                    INSERT INTO student_courses (student_email, course_id)
                    VALUES (%s, %s)
                    ON CONFLICT (student_email, course_id) DO NOTHING
                    """,
                    (student_email, course_id),
                )
            for activity_no, title, status in activities:
                cursor.execute(
                    """
                    INSERT INTO activities (course_id, activity_no, title, status)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (course_id, activity_no) DO UPDATE
                    SET title = EXCLUDED.title,
                        status = EXCLUDED.status
                    """,
                    (course_id, activity_no, title, status),
                )


def _validate_course_ownership(
    cursor: Any,
    course_id: str,
    role: str,
    user_email: str,
) -> str:
    normalized_course_id = course_id.strip().lower()
    if not normalized_course_id:
        raise CourseAccessError("Course id is required")

    cursor.execute(
        """
        SELECT course_id
        FROM courses
        WHERE LOWER(course_id) = LOWER(%s)
        """,
        (normalized_course_id,),
    )
    course = _fetch_one_as_dict(cursor)
    if course is None:
        raise CourseNotFoundError("Course was not found")

    course_id_from_db = course["course_id"]
    if role == "instructor":
        access_table = "instructor_courses"
        email_column = "instructor_email"
    elif role == "student":
        access_table = "student_courses"
        email_column = "student_email"
    else:
        raise CourseAccessError("Unsupported course role")

    cursor.execute(
        f"""
        SELECT 1
        FROM {access_table}
        WHERE LOWER({email_column}) = LOWER(%s)
          AND LOWER(course_id) = LOWER(%s)
        """,
        (user_email, course_id_from_db),
    )
    if cursor.fetchone() is None:
        raise CourseAccessError("User is not authorized to access this course")

    return course_id_from_db


def verify_google_token(token: str) -> dict[str, Any]:
    if not token:
        raise AuthError("Google ID token is required")

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise AuthError("GOOGLE_CLIENT_ID is not configured")

    try:
        payload = id_token.verify_oauth2_token(token, requests.Request(), client_id)
    except ValueError as exc:
        raise AuthError("Invalid Google ID token") from exc

    if not payload.get("email_verified"):
        raise AuthError("Google account email is not verified")

    email = payload.get("email")
    if not email:
        raise AuthError("Google token does not contain an email")

    return payload


def map_to_instructor_account(payload: dict[str, Any]) -> InstructorUser:
    email = str(payload["email"]).lower()
    allowed_emails = _allowed_instructor_emails()

    if allowed_emails and email not in allowed_emails:
        raise AuthError("Google identity is not mapped to an instructor account")

    return InstructorUser(
        email=email,
        name=payload.get("name"),
        google_sub=payload.get("sub"),
    )


def map_to_student_account(payload: dict[str, Any]) -> StudentUser:
    email = str(payload["email"]).lower()
    allowed_emails = _allowed_student_emails()

    if allowed_emails and email not in allowed_emails:
        raise AuthError("Google identity is not mapped to a student account")

    return StudentUser(
        email=email,
        name=payload.get("name"),
        google_sub=payload.get("sub"),
    )


def instructor_google_login(token: str) -> dict[str, Any]:
    payload = verify_google_token(token)
    instructor = map_to_instructor_account(payload)

    return {
        "ok": True,
        "role": "instructor",
        "email": instructor.email,
        "name": instructor.name,
        "google_sub": instructor.google_sub,
    }


def student_google_login(token: str) -> dict[str, Any]:
    payload = verify_google_token(token)
    student = map_to_student_account(payload)

    return {
        "ok": True,
        "role": "student",
        "email": student.email,
        "name": student.name,
        "google_sub": student.google_sub,
    }


def list_activities(
    course_id: str,
    role: str,
    user_email: str,
) -> list[dict[str, Any]]:
    if _use_memory_activity_store():
        course_id_from_store = _memory_course_id(course_id)
        _seed_memory_activity_data()
        return sorted(
            (
                activity.copy()
                for activity in _memory_activities[course_id_from_store]
            ),
            key=lambda activity: (
                activity["activity_no"],
                activity["title"].lower(),
            ),
        )

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role=role,
                user_email=user_email,
            )
            cursor.execute(
                """
                SELECT course_id, activity_no, title, status
                FROM activities
                WHERE LOWER(course_id) = LOWER(%s)
                ORDER BY activity_no ASC, LOWER(title) ASC, activity_id ASC
                """,
                (course_id_from_db,),
            )
            return _fetch_all_as_dicts(cursor)
def create_activity(
    course_id: str,
    activity_no: int,
    title: str,
    status: str,
    role: str,
    user_email: str,
) -> dict[str, Any]:
    VALID_STATUSES = {"NOT_STARTED", "ACTIVE", "ENDED"}

    # Validate required fields
    if not course_id or not course_id.strip():
        raise ValueError("course_id is required")
    if not title or not title.strip():
        raise ValueError("title is required")
    if activity_no is None:
        raise ValueError("activity_no is required")
    if activity_no < 1:
        raise ValueError("activity_no must be a positive integer")
    if status not in VALID_STATUSES:
        raise ValueError(f"status must be one of {sorted(VALID_STATUSES)}")

    if _use_memory_activity_store():
        course_id_from_store = _memory_course_id(course_id)
        _seed_memory_activity_data()
        activities = _memory_activities[course_id_from_store]
        if any(activity["activity_no"] == activity_no for activity in activities):
            raise ValueError(
                f"activity_no {activity_no} already exists in this course"
            )

        activity = {
            "course_id": course_id_from_store,
            "activity_no": activity_no,
            "title": title.strip(),
            "status": status,
        }
        activities.append(activity)
        return activity.copy()

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            # Validate course access
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role=role,
                user_email=user_email,
            )

            # Prevent duplicate activity_no
            cursor.execute(
                """
                SELECT 1 FROM activities
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            if cursor.fetchone() is not None:
                raise ValueError(
                    f"activity_no {activity_no} already exists in this course"
                )

            # Store in DB
            cursor.execute(
                """
                INSERT INTO activities (course_id, activity_no, title, status)
                VALUES (%s, %s, %s, %s)
                RETURNING course_id, activity_no, title, status
                """,
                (course_id_from_db, activity_no, title.strip(), status),
            )
            return _fetch_one_as_dict(cursor)


def update_activity(
    course_id: str,
    activity_no: int,
    updates: dict[str, Any],
    role: str,
    user_email: str,
) -> dict[str, Any]:
    valid_statuses = {"NOT_STARTED", "ACTIVE", "ENDED"}
    editable_fields = {"activity_no", "title", "status"}
    protected_fields = {
        "id",
        "activity_id",
        "course_id",
        "owner",
        "owner_id",
        "owner_email",
        "user",
        "user_id",
        "user_email",
        "created_at",
        "updated_at",
    }

    if not course_id or not course_id.strip():
        raise ValueError("course_id is required")
    if activity_no < 1:
        raise ValueError("activity_no must be a positive integer")
    if not updates:
        raise ValueError("Update request must include at least one editable field")

    blocked_fields = protected_fields.intersection(updates)
    if blocked_fields:
        raise ValueError(
            f"Protected fields cannot be updated: {sorted(blocked_fields)}"
        )

    unsupported_fields = set(updates) - editable_fields
    if unsupported_fields:
        raise ValueError(
            f"Unsupported activity fields: {sorted(unsupported_fields)}"
        )

    normalized_updates: dict[str, Any] = {}
    if "activity_no" in updates:
        new_activity_no = updates["activity_no"]
        if (
            not isinstance(new_activity_no, int)
            or isinstance(new_activity_no, bool)
            or new_activity_no < 1
        ):
            raise ValueError("activity_no must be a positive integer")
        normalized_updates["activity_no"] = new_activity_no
    if "title" in updates:
        title = updates["title"]
        if not isinstance(title, str) or not title.strip():
            raise ValueError("title is required")
        normalized_updates["title"] = title.strip()
    if "status" in updates:
        status = updates["status"]
        if not isinstance(status, str) or status not in valid_statuses:
            raise ValueError(f"status must be one of {sorted(valid_statuses)}")
        normalized_updates["status"] = status

    if _use_memory_activity_store():
        course_id_from_store = _memory_course_id(course_id)
        _seed_memory_activity_data()
        activities = _memory_activities[course_id_from_store]
        activity = next(
            (
                stored_activity
                for stored_activity in activities
                if stored_activity["activity_no"] == activity_no
            ),
            None,
        )
        if activity is None:
            raise ActivityNotFoundError("Activity was not found")

        if (
            "activity_no" in normalized_updates
            and normalized_updates["activity_no"] != activity_no
            and any(
                stored_activity["activity_no"] == normalized_updates["activity_no"]
                for stored_activity in activities
            )
        ):
            raise ValueError(
                f"activity_no {normalized_updates['activity_no']} already exists in this course"
            )

        activity.update(normalized_updates)
        return activity.copy()

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role=role,
                user_email=user_email,
            )

            cursor.execute(
                """
                SELECT activity_id
                FROM activities
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            activity = _fetch_one_as_dict(cursor)
            if activity is None:
                raise ActivityNotFoundError("Activity was not found")

            if (
                "activity_no" in normalized_updates
                and normalized_updates["activity_no"] != activity_no
            ):
                cursor.execute(
                    """
                    SELECT 1 FROM activities
                    WHERE LOWER(course_id) = LOWER(%s)
                      AND activity_no = %s
                    """,
                    (course_id_from_db, normalized_updates["activity_no"]),
                )
                if cursor.fetchone() is not None:
                    raise ValueError(
                        f"activity_no {normalized_updates['activity_no']} already exists in this course"
                    )

            set_clause = ", ".join(
                f"{field} = %s" for field in normalized_updates
            )
            values = list(normalized_updates.values())
            values.append(activity["activity_id"])
            cursor.execute(
                f"""
                UPDATE activities
                SET {set_clause}
                WHERE activity_id = %s
                RETURNING course_id, activity_no, title, status
                """,
                values,
            )
            return _fetch_one_as_dict(cursor)
