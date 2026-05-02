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
    return explicit_emails or _allowed_instructor_emails()


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
