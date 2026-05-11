import json
import os
import re
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Dict

from google.auth.transport import requests
from google.oauth2 import id_token


class AuthError(ValueError):
    pass


class CourseAccessError(ValueError):
    pass


class CourseNotFoundError(CourseAccessError):
    pass


class ActivityAccessError(ValueError):
    pass


class EnglishResponseError(ValueError):
    pass


class DatabaseConfigError(RuntimeError):
    pass


MAX_TUTORING_STEPS = 3
_TURKISH_CHARACTERS = set("\u00e7\u011f\u0131\u00f6\u015f\u00fc\u00c7\u011e\u0130\u00d6\u015e\u00dc")
_COMMON_NON_ENGLISH_WORDS = {
    "ama",
    "ben",
    "bence",
    "bir",
    "bu",
    "cunku",
    "degil",
    "ders",
    "evet",
    "hayir",
    "icin",
    "ile",
}
_QUESTION_FOCUS_STOP_WORDS = {
    "about",
    "activity",
    "answer",
    "because",
    "detail",
    "explain",
    "from",
    "have",
    "learned",
    "main",
    "must",
    "strongest",
    "system",
    "that",
    "their",
    "there",
    "this",
    "what",
    "with",
}


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
    explicit_emails = {email.strip().lower() for email in raw.split(",") if email.strip()}
    return explicit_emails or _allowed_instructor_emails()


def _demo_student_emails() -> set[str]:
    raw = os.getenv("DEMO_STUDENT_EMAILS", "")
    explicit_emails = {email.strip().lower() for email in raw.split(",") if email.strip()}
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


def _activity_text(activity: dict[str, Any]) -> str:
    text = str(activity.get("activity_text") or "").strip()
    if text:
        return text
    return f"Read the activity titled '{activity['title']}' and answer the tutor question."


def _load_activity(
    cursor: Any,
    course_id: str,
    activity_no: int,
) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT course_id, activity_no, title, activity_text, status
        FROM activities
        WHERE LOWER(course_id) = LOWER(%s)
          AND activity_no = %s
        """,
        (course_id, activity_no),
    )

    activity = _fetch_one_as_dict(cursor)
    if activity is None:
        raise ActivityAccessError("Activity was not found")

    return activity


def _ensure_active_activity(activity: dict[str, Any]) -> None:
    if activity["status"] == "NOT_STARTED":
        raise ActivityAccessError("Activity is not active yet")

    if activity["status"] == "ENDED":
        raise ActivityAccessError("Activity has ended")


def _clean_answer(answer: str | None) -> str:
    cleaned = (answer or "").strip()
    if not cleaned:
        raise EnglishResponseError("Answer is required before continuing")
    return cleaned


def _looks_like_english(answer: str) -> bool:
    if any(character in _TURKISH_CHARACTERS for character in answer):
        return False

    letters = [character for character in answer if character.isalpha()]
    if len(letters) < 3:
        return False

    ascii_letters = sum(1 for character in letters if character.isascii())
    if ascii_letters / len(letters) < 0.85:
        return False

    words = {
        word
        for word in re.findall(r"[a-zA-Z]+", answer.lower())
        if len(word) > 1
    }
    if words & _COMMON_NON_ENGLISH_WORDS:
        return False

    return True


def _require_english_answer(answer: str | None) -> str:
    cleaned = _clean_answer(answer)
    if not _looks_like_english(cleaned):
        raise EnglishResponseError("Please answer in English before continuing")
    return cleaned


def _load_progress(
    cursor: Any,
    course_id: str,
    activity_no: int,
    student_email: str,
) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT student_email, course_id, activity_no, step_no, status, last_question, history
        FROM student_activity_progress
        WHERE LOWER(student_email) = LOWER(%s)
          AND LOWER(course_id) = LOWER(%s)
          AND activity_no = %s
        """,
        (student_email, course_id, activity_no),
    )
    return _fetch_one_as_dict(cursor)


def _decode_history(progress: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not progress:
        return []

    try:
        history = json.loads(progress.get("history") or "[]")
    except json.JSONDecodeError:
        return []

    if isinstance(history, list):
        return [item for item in history if isinstance(item, dict)]

    return []


def _answer_focus(answer: str | None) -> str:
    if not answer:
        return "your answer"

    words = [
        word
        for word in re.findall(r"[a-zA-Z]+", answer.lower())
        if len(word) > 3 and word not in _QUESTION_FOCUS_STOP_WORDS
    ]
    if not words:
        return "your answer"

    unique_words = list(dict.fromkeys(words))
    return " ".join(unique_words[:3])


def _generate_tutoring_question(
    activity: dict[str, Any],
    step_no: int,
    previous_answer: str | None = None,
) -> str:
    if step_no == 0:
        return "What is the main idea of this activity?"

    answer_focus = _answer_focus(previous_answer)
    if step_no == 1:
        return f"Which detail from the activity best supports your point about {answer_focus}?"

    if step_no == 2:
        return f"How would you apply your point about {answer_focus} in your project?"

    if previous_answer:
        return f"What is one improvement you can make to your point about {answer_focus}?"

    return "What should you focus on next in this activity?"


def _tutoring_response(
    activity: dict[str, Any],
    progress_status: str,
    step_no: int,
    question: str | None,
    message: str,
) -> dict[str, Any]:
    return {
        "course_id": activity["course_id"],
        "activity_no": activity["activity_no"],
        "title": activity["title"],
        "activity_text": _activity_text(activity),
        "status": activity["status"],
        "step_no": step_no,
        "progress_status": progress_status,
        "question": question,
        "message": message,
    }


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
                    course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                    PRIMARY KEY (instructor_email, course_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS student_courses (
                    student_email TEXT NOT NULL,
                    course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                    PRIMARY KEY (student_email, course_id)
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS activities (
                    activity_id BIGSERIAL PRIMARY KEY,
                    course_id TEXT NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
                    activity_no INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    activity_text TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK (status IN ('NOT_STARTED', 'ACTIVE', 'ENDED')),
                    UNIQUE (course_id, activity_no)
                )
                """
            )
            cursor.execute(
                """
                ALTER TABLE activities
                ADD COLUMN IF NOT EXISTS activity_text TEXT NOT NULL DEFAULT ''
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS student_activity_progress (
                    progress_id BIGSERIAL PRIMARY KEY,
                    student_email TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    activity_no INTEGER NOT NULL,
                    step_no INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL CHECK (status IN ('IN_PROGRESS', 'COMPLETED')),
                    last_question TEXT,
                    history TEXT NOT NULL DEFAULT '[]',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (student_email, course_id, activity_no),
                    FOREIGN KEY (course_id, activity_no)
                        REFERENCES activities(course_id, activity_no)
                        ON DELETE CASCADE
                )
                """
            )


def seed_demo_activity_data() -> None:
    course_id = _demo_course_id()
    course_name = _demo_course_name()
    activities = (
        (
            1,
            "Project proposal",
            "NOT_STARTED",
            "Read the project proposal prompt and prepare to explain the problem, target users, and success criteria.",
        ),
        (
            2,
            "Requirements analysis",
            "ACTIVE",
            "Review the requirements analysis activity. Focus on identifying functional requirements, non-functional requirements, and unclear assumptions.",
        ),
        (
            3,
            "Sprint planning",
            "ENDED",
            "Reflect on sprint planning by connecting backlog items to concrete tasks, owners, and acceptance criteria.",
        ),
    )

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO courses (course_id, name)
                VALUES (%s, %s)
                ON CONFLICT (course_id) DO UPDATE SET name = EXCLUDED.name
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

            for activity_no, title, status, activity_text in activities:
                cursor.execute(
                    """
                    INSERT INTO activities (course_id, activity_no, title, status, activity_text)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (course_id, activity_no) DO UPDATE
                    SET title = EXCLUDED.title,
                        status = EXCLUDED.status,
                        activity_text = EXCLUDED.activity_text
                    """,
                    (course_id, activity_no, title, status, activity_text),
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

    return InstructorUser(email=email, name=payload.get("name"), google_sub=payload.get("sub"))


def map_to_student_account(payload: dict[str, Any]) -> StudentUser:
    email = str(payload["email"]).lower()
    allowed_emails = _allowed_student_emails()

    if allowed_emails and email not in allowed_emails:
        raise AuthError("Google identity is not mapped to a student account")

    return StudentUser(email=email, name=payload.get("name"), google_sub=payload.get("sub"))


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


def list_activities(course_id: str, role: str, user_email: str) -> list[dict[str, Any]]:
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


def get_active_activity_for_student(
    course_id: str,
    activity_no: int,
    student_email: str,
) -> dict[str, Any]:
    with _db_connection() as connection:
        with connection.cursor() as cursor:
            # Validate student enrollment before returning any activity data.
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role="student",
                user_email=student_email,
            )

            activity = _load_activity(cursor, course_id_from_db, activity_no)
            _ensure_active_activity(activity)

            return {
                "course_id": activity["course_id"],
                "activity_no": activity["activity_no"],
                "title": activity["title"],
                "activity_text": _activity_text(activity),
                "status": activity["status"],
            }


def run_tutoring_turn(
    course_id: str,
    activity_no: int,
    student_email: str,
    answer: str | None = None,
) -> dict[str, Any]:
    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role="student",
                user_email=student_email,
            )
            activity = _load_activity(cursor, course_id_from_db, activity_no)
            _ensure_active_activity(activity)

            progress = _load_progress(
                cursor=cursor,
                course_id=course_id_from_db,
                activity_no=activity_no,
                student_email=student_email,
            )

            if progress is None:
                question = _generate_tutoring_question(activity, step_no=0)
                cursor.execute(
                    """
                    INSERT INTO student_activity_progress (
                        student_email,
                        course_id,
                        activity_no,
                        step_no,
                        status,
                        last_question,
                        history
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        student_email,
                        course_id_from_db,
                        activity_no,
                        0,
                        "IN_PROGRESS",
                        question,
                        "[]",
                    ),
                )
                return _tutoring_response(
                    activity=activity,
                    progress_status="IN_PROGRESS",
                    step_no=0,
                    question=question,
                    message="Activity text is shown before the first tutor question",
                )

            if progress["status"] == "COMPLETED":
                return _tutoring_response(
                    activity=activity,
                    progress_status="COMPLETED",
                    step_no=progress["step_no"],
                    question=None,
                    message="Tutoring flow is already completed",
                )

            if answer is None:
                return _tutoring_response(
                    activity=activity,
                    progress_status=progress["status"],
                    step_no=progress["step_no"],
                    question=progress["last_question"],
                    message="Answer the current question to continue",
                )

            cleaned_answer = _require_english_answer(answer)
            history = _decode_history(progress)
            history.append(
                {
                    "step_no": progress["step_no"],
                    "question": progress["last_question"],
                    "answer": cleaned_answer,
                }
            )

            next_step_no = progress["step_no"] + 1
            if next_step_no >= MAX_TUTORING_STEPS:
                next_status = "COMPLETED"
                next_question = None
                message = "Tutoring flow completed"
            else:
                next_status = "IN_PROGRESS"
                next_question = _generate_tutoring_question(
                    activity=activity,
                    step_no=next_step_no,
                    previous_answer=cleaned_answer,
                )
                message = "Follow-up question generated"

            cursor.execute(
                """
                UPDATE student_activity_progress
                SET step_no = %s,
                    status = %s,
                    last_question = %s,
                    history = %s,
                    updated_at = NOW()
                WHERE LOWER(student_email) = LOWER(%s)
                  AND LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (
                    next_step_no,
                    next_status,
                    next_question,
                    json.dumps(history),
                    student_email,
                    course_id_from_db,
                    activity_no,
                ),
            )

            return _tutoring_response(
                activity=activity,
                progress_status=next_status,
                step_no=next_step_no,
                question=next_question,
                message=message,
            )


def _update_activity_in_db(
    course_id: str,
    activity_no: int,
    updates: Dict[str, Any],
    role: str,
    user_email: str,
) -> Dict[str, Any]:
    allowed_fields = {"title", "status", "activity_text"}
    update_values = {
        key: value
        for key, value in updates.items()
        if key in allowed_fields and value is not None
    }

    if not update_values:
        raise ActivityAccessError("No supported activity updates were provided")

    if "status" in update_values and update_values["status"] not in {
        "NOT_STARTED",
        "ACTIVE",
        "ENDED",
    }:
        raise ActivityAccessError("Unsupported activity status")

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role=role,
                user_email=user_email,
            )
            _load_activity(cursor, course_id_from_db, activity_no)

            assignments = ", ".join(f"{field} = %s" for field in update_values)
            values = list(update_values.values())
            cursor.execute(
                f"""
                UPDATE activities
                SET {assignments}
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                RETURNING course_id, activity_no, title, activity_text, status
                """,
                (*values, course_id_from_db, activity_no),
            )

            updated_activity = _fetch_one_as_dict(cursor)
            if updated_activity is None:
                raise ActivityAccessError("Activity was not found")

            return {
                "course_id": updated_activity["course_id"],
                "activity_no": updated_activity["activity_no"],
                "title": updated_activity["title"],
                "activity_text": _activity_text(updated_activity),
                "status": updated_activity["status"],
            }


def update_activity(
    course_id: str,
    activity_no: int,
    updates: Dict[str, Any],
    role: str,
    user_email: str,
) -> Dict[str, Any]:
    return _update_activity_in_db(
        course_id=course_id,
        activity_no=activity_no,
        updates=updates,
        role=role,
        user_email=user_email,
    )
