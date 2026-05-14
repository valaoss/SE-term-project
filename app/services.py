import json
import os
import re
import urllib.error
import urllib.request
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
_LOW_QUALITY_ANSWER_PATTERNS = {
    "d",
    "idk",
    "i dont know",
    "i don't know",
    "dont know",
    "don't know",
    "no idea",
    "not sure",
    "bilmem",
}

# Mini-lessons shown after each objective is achieved (index = step_no)
_MINI_LESSONS = [
    "Mini-lesson: Break complex topics into smaller ideas before answering.",
    "Mini-lesson: Always connect your answer back to the activity context.",
    "Mini-lesson: Review your previous answers to deepen your understanding.",
]
_MEMORY_STORE: dict[str, Any] | None = None
_GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"


def _max_steps_for_activity(activity: dict[str, Any]) -> int:
    return max(len(_decode_learning_objectives(activity.get("learning_objectives"))), 1)


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
    return explicit_emails or _allowed_instructor_emails() or {"instructor@mef.edu.tr"}


def _demo_student_emails() -> set[str]:
    raw = os.getenv("DEMO_STUDENT_EMAILS", "")
    explicit_emails = {email.strip().lower() for email in raw.split(",") if email.strip()}
    return explicit_emails or _allowed_student_emails() or {"student@mef.edu.tr"}


def _database_url() -> str:
    database_url = os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    if not database_url:
        raise DatabaseConfigError("DATABASE_URL is not configured")
    return database_url


def _use_memory_store() -> bool:
    return os.getenv("INCLASS_MEMORY_STORE", "1") == "1" and not (
        os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL")
    )


def _memory_store() -> dict[str, Any]:
    global _MEMORY_STORE
    if _MEMORY_STORE is not None:
        return _MEMORY_STORE

    course_id = _demo_course_id()
    _MEMORY_STORE = {
        "courses": {
            course_id: {
                "course_id": course_id,
                "name": _demo_course_name(),
            }
        },
        "instructor_courses": {
            email: {course_id}
            for email in (_demo_instructor_emails() | {"instructor@mef.edu.tr"})
        },
        "student_courses": {
            email: {course_id}
            for email in (_demo_student_emails() | {"student@mef.edu.tr"})
        },
        "activities": {
            (course_id, 1): {
                "course_id": course_id,
                "activity_no": 1,
                "title": "Project proposal",
                "activity_text": "Explain the problem, target users, and success criteria for your project proposal.",
                "learning_objectives": json.dumps(
                    [
                        "Identify the project problem",
                        "Describe target users",
                        "Define success criteria",
                    ]
                ),
                "status": "NOT_STARTED",
            },
            (course_id, 2): {
                "course_id": course_id,
                "activity_no": 2,
                "title": "Requirements analysis",
                "activity_text": "Review the requirements activity and explain functional requirements, non-functional requirements, and unclear assumptions.",
                "learning_objectives": json.dumps(
                    [
                        "Distinguish functional requirements",
                        "Distinguish non-functional requirements",
                        "Identify unclear assumptions",
                    ]
                ),
                "status": "ACTIVE",
            },
            (course_id, 3): {
                "course_id": course_id,
                "activity_no": 3,
                "title": "Sprint planning",
                "activity_text": "Connect backlog items to concrete tasks, owners, and acceptance criteria.",
                "learning_objectives": json.dumps(
                    [
                        "Connect backlog items to tasks",
                        "Assign implementation ownership",
                        "Write acceptance criteria",
                    ]
                ),
                "status": "ENDED",
            },
        },
        "progress": {},
        "score_logs": [],
        "manual_grading_events": [],
    }
    return _MEMORY_STORE


def _memory_validate_course_ownership(store: dict[str, Any], course_id: str, role: str, user_email: str) -> str:
    normalized_course_id = course_id.strip().lower()
    course = next(
        (
            item
            for item in store["courses"].values()
            if item["course_id"].lower() == normalized_course_id
        ),
        None,
    )
    if course is None:
        raise CourseNotFoundError("Course was not found")

    access_key = "instructor_courses" if role == "instructor" else "student_courses"
    user_courses = store[access_key].get(user_email.strip().lower(), set())
    if course["course_id"] not in user_courses:
        raise CourseAccessError("User is not authorized to access this course")
    return course["course_id"]


def _memory_load_activity(store: dict[str, Any], course_id: str, activity_no: int) -> dict[str, Any]:
    activity = store["activities"].get((course_id, activity_no))
    if activity is None:
        raise ActivityAccessError("Activity was not found")
    return dict(activity)


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


def _encode_learning_objectives(objectives: list[str]) -> str:
    clean_objectives = [
        objective.strip()
        for objective in objectives
        if isinstance(objective, str) and objective.strip()
    ]
    if not clean_objectives:
        raise ActivityAccessError("At least one learning objective is required")
    return json.dumps(clean_objectives)


def _decode_learning_objectives(raw_objectives: Any) -> list[str]:
    if isinstance(raw_objectives, list):
        return [str(objective) for objective in raw_objectives if str(objective).strip()]

    try:
        objectives = json.loads(raw_objectives or "[]")
    except json.JSONDecodeError:
        return []

    if not isinstance(objectives, list):
        return []

    return [str(objective) for objective in objectives if str(objective).strip()]


def _activity_response(activity: dict[str, Any], include_objectives: bool = False) -> dict[str, Any]:
    response = {
        "course_id": activity["course_id"],
        "activity_no": activity["activity_no"],
        "title": activity["title"],
        "activity_text": _activity_text(activity),
        "status": activity["status"],
    }
    if include_objectives:
        response["learning_objectives"] = _decode_learning_objectives(
            activity.get("learning_objectives")
        )
    return response


def _load_activity(
    cursor: Any,
    course_id: str,
    activity_no: int,
) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT course_id, activity_no, title, activity_text, learning_objectives, status
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
        raise ActivityAccessError("This activity has not started yet. Wait for the instructor to activate it.")

    if activity["status"] == "ENDED":
        raise ActivityAccessError("This activity has ended and cannot accept new responses.")


def _ensure_activity_allows_scoring(activity: dict[str, Any]) -> None:
    if activity["status"] == "ENDED":
        raise ActivityAccessError("Ended activities cannot accept new score logs")


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


def _answer_meets_minimum_quality(answer: str) -> bool:
    normalized = re.sub(r"[^a-zA-Z' ]+", " ", answer.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if normalized in _LOW_QUALITY_ANSWER_PATTERNS:
        return False

    words = re.findall(r"[a-zA-Z]+", normalized)
    meaningful_words = [word for word in words if len(word) > 2]
    return len(meaningful_words) >= 4


def _fallback_tutoring_feedback(
    activity: dict[str, Any],
    progress: dict[str, Any],
    answer: str,
) -> dict[str, Any]:
    if not _answer_meets_minimum_quality(answer):
        return {
            "objective_achieved": False,
            "feedback": (
                "That answer is too short to show understanding. Add a specific idea "
                "from the activity before moving on."
            ),
            "next_question": progress.get("last_question")
            or _generate_tutoring_question(activity, progress["step_no"]),
            "mini_lesson": "",
        }

    return {
        "objective_achieved": True,
        "feedback": None,
        "next_question": None,
        "mini_lesson": "",
    }


def _load_progress(
    cursor: Any,
    course_id: str,
    activity_no: int,
    student_email: str,
) -> dict[str, Any] | None:
    cursor.execute(
        """
        SELECT student_email, course_id, activity_no, step_no, status,
               last_question, last_answer, history, score, achieved_objectives
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


# --- US-K Scoring: Track objectives per student ---
def _decode_achieved_objectives(progress: dict[str, Any] | None) -> list[int]:
    """Return the list of step_no values that have already been scored."""
    if not progress:
        return []
    try:
        objectives = json.loads(progress.get("achieved_objectives") or "[]")
    except json.JSONDecodeError:
        return []
    if isinstance(objectives, list):
        return [o for o in objectives if isinstance(o, int)]
    return []


# --- US-K Scoring: Log every score change ---
def _log_score_change(
    cursor: Any,
    student_email: str,
    course_id: str,
    activity_no: int,
    step_no: int,
    new_score: int,
    objective_text: str = "",
    event_type: str = "objective_achieved",
) -> None:
    cursor.execute(
        """
        INSERT INTO score_logs (student_email, course_id, activity_no, step_no, new_score, objective_text, event_type)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (student_email, course_id, activity_no, step_no, new_score, objective_text, event_type),
    )


def _log_manual_grading_event(
    cursor: Any,
    instructor_email: str,
    student_email: str,
    course_id: str,
    activity_no: int,
    old_score: int | None,
    new_score: int,
    reason: str | None,
) -> None:
    cursor.execute(
        """
        INSERT INTO manual_grading_events (
            instructor_email,
            student_email,
            course_id,
            activity_no,
            old_score,
            new_score,
            reason
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            instructor_email,
            student_email,
            course_id,
            activity_no,
            old_score,
            new_score,
            reason,
        ),
    )


# --- US-K Scoring: Trigger mini-lesson after scoring ---
def _generate_mini_lesson(step_no: int, objective_text: str = "") -> str:
    if objective_text:
        return f"Key takeaway: {objective_text} — keep this concept in mind as you progress."
    return _MINI_LESSONS[step_no % len(_MINI_LESSONS)]


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


def _ai_generate_tutoring_question(
    activity: dict[str, Any],
    step_no: int,
    previous_answer: str | None,
) -> str | None:
    objectives = _decode_learning_objectives(activity.get("learning_objectives"))
    current_objective = objectives[step_no] if step_no < len(objectives) else "the key concept"
    messages = [
        {
            "role": "system",
            "content": (
                "You are an InClass tutor. Generate ONE focused, open-ended question to assess the student's "
                "understanding of the given learning objective. The question must require the student to explain "
                "in their own words. Return ONLY valid JSON: {\"question\": str}"
            ),
        },
        {
            "role": "user",
            "content": json.dumps({
                "activity_title": activity["title"],
                "learning_objective": current_objective,
                "step_no": step_no,
                "previous_answer": previous_answer or "",
            }),
        },
    ]
    result = _call_groq(messages)
    if result and isinstance(result.get("question"), str):
        q = result["question"].strip()
        return q if q else None
    return None


def _generate_tutoring_question(
    activity: dict[str, Any],
    step_no: int,
    previous_answer: str | None = None,
) -> str:
    ai_q = _ai_generate_tutoring_question(activity, step_no, previous_answer)
    if ai_q:
        return ai_q

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


def _groq_api_key() -> str | None:
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    return api_key or None


def _groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.1-8b-instant").strip() or "llama-3.1-8b-instant"


def _groq_enabled() -> bool:
    return _groq_api_key() is not None


def tutoring_provider_status() -> dict[str, Any]:
    return {
        "ai_enabled": _groq_enabled(),
        "ai_provider": "groq" if _groq_enabled() else "rule-based",
        "ai_model": _groq_model() if _groq_enabled() else None,
    }


def _call_groq(messages: list[dict[str, str]]) -> dict[str, Any] | None:
    api_key = _groq_api_key()
    if not api_key:
        return None

    payload = {
        "model": _groq_model(),
        "messages": messages,
        "temperature": 0.35,
        "max_tokens": 700,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        _GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            raw_response = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None

    try:
        content = raw_response["choices"][0]["message"]["content"]
        parsed = json.loads(content)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError):
        return None

    if not isinstance(parsed, dict):
        return None
    return parsed


def _call_groq_text(messages: list[dict[str, str]]) -> str | None:
    """Like _call_groq but returns plain text instead of JSON."""
    api_key = _groq_api_key()
    if not api_key:
        return None

    payload = {
        "model": _groq_model(),
        "messages": messages,
        "temperature": 0.0,
        "max_tokens": 10,
    }
    request = urllib.request.Request(
        _GROQ_API_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = json.loads(response.read().decode("utf-8"))
            return raw["choices"][0]["message"]["content"].strip().upper()
    except Exception:
        return None


def _ai_verify_relevance(answer: str, activity: dict[str, Any]) -> bool:
    """Ask the AI: is this answer genuinely about the activity topic? Returns True if YES."""
    if not _groq_enabled():
        return True  # Can't check without AI, let backend keyword check handle it

    activity_title = activity.get("title", "")
    activity_text = _activity_text(activity)[:400]  # First 400 chars is enough

    system = (
        "You are a strict relevance checker. "
        "Answer with exactly one word: YES or NO. No explanation."
    )
    user = (
        f"Activity topic: \"{activity_title}\"\n"
        f"Activity description: \"{activity_text}\"\n"
        f"Student answer: \"{answer}\"\n\n"
        "Does the student's answer genuinely address the activity topic with relevant content? "
        "If the answer is off-topic, copied text, keyword spam, or unrelated to the activity — answer NO. "
        "Answer YES or NO only."
    )
    result = _call_groq_text([
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ])
    if result is None:
        return True  # Fallback: don't block if AI unavailable
    return result.startswith("YES")


def _ai_tutoring_feedback(
    activity: dict[str, Any],
    progress: dict[str, Any],
    answer: str,
    achieved_objectives: list[int],
) -> dict[str, Any] | None:
    objectives = _decode_learning_objectives(activity.get("learning_objectives"))
    current_step = progress["step_no"]
    current_objective = objectives[current_step] if current_step < len(objectives) else "the key concept"

    prompt = {
        "activity_title": activity["title"],
        "activity_text": _activity_text(activity),
        "current_objective": current_objective,
        "current_step_no": current_step,
        "total_steps": len(objectives),
        "question_asked": progress.get("last_question"),
        "student_answer": answer,
        "already_scored_steps": len(achieved_objectives),
    }
    system = (
        "You are a STRICT InClass AI tutor. Your job is to RIGOROUSLY evaluate whether the student "
        "genuinely understands the concept — not just whether they mentioned the right words.\n\n"

        "AUTOMATIC REJECT — set objective_achieved=false immediately if ANY of these are true:\n"
        "1. Answer contains phrases like 'keep this concept in mind', 'key takeaway', 'as you progress', "
        "'[Groq AI]', 'Score:', 'Final score', 'Activity complete' — these are AI-generated texts being copy-pasted back.\n"
        "2. Answer is fewer than 15 words.\n"
        "3. Answer is a single bullet point or list with no explanatory sentences.\n"
        "4. Answer repeats the question verbatim without explaining.\n"
        "5. Answer does not contain any reasoning, cause-effect relationship, or 'because/since/therefore' type logic.\n\n"

        "RULE 1 — Must directly answer question_asked:\n"
        "The student must address the specific question with explanation. "
        "Vague, off-topic, or question-ignoring answers → objective_achieved=false.\n\n"

        "RULE 2 — Must show genuine understanding:\n"
        "Student must explain WHY or HOW in their own words. "
        "Simply naming or listing concepts without explanation → objective_achieved=false. "
        "Give specific feedback pointing to what is missing.\n\n"

        "RULE 3 — Must match current_objective:\n"
        "objective_achieved=true ONLY IF student clearly demonstrated understanding of current_objective "
        "through their own reasoning.\n\n"

        "OUTPUT: Return ONLY valid JSON:\n"
        "{\"objective_achieved\": bool, \"feedback\": str, \"next_question\": str|null, \"mini_lesson\": str, "
        "\"related_topics\": [str, str, str], \"alternative_techniques\": [str, str, str]}\n"
        "- feedback: Specific critique pointing to what the student got right/wrong. Be direct, not generic.\n"
        "- next_question: If objective_achieved=true, ask about the NEXT concept. "
        "If false, rephrase the same question from a different angle. Never null.\n"
        "- mini_lesson: ONE sentence insight if objective_achieved=true, else empty string.\n"
        "- related_topics: 3 VERY SHORT labels (2-3 words max, e.g. 'Use Case Diagrams', 'Agile Sprints').\n"
        "- alternative_techniques: 3 SHORT action phrases (4-5 words, e.g. 'Draw a system diagram', 'Compare two examples').\n"
        "- All output in English only.\n"
        "- Do NOT reveal current_objective verbatim."
    )
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(prompt)},
    ]
    result = _call_groq(messages)
    if result is None:
        return None

    def _clean_list(val: Any, max_items: int = 3) -> list[str]:
        if not isinstance(val, list):
            return []
        return [str(x).strip() for x in val if isinstance(x, str) and str(x).strip()][:max_items]

    return {
        "objective_achieved": bool(result.get("objective_achieved")),
        "feedback": str(result.get("feedback") or "Answer received."),
        "next_question": (
            str(result["next_question"]).strip()
            if result.get("next_question") is not None
            else None
        ),
        "mini_lesson": str(result.get("mini_lesson") or "").strip(),
        "related_topics": _clean_list(result.get("related_topics")),
        "alternative_techniques": _clean_list(result.get("alternative_techniques")),
    }


def _tutoring_response(
    activity: dict[str, Any],
    progress_status: str,
    step_no: int,
    question: str | None,
    message: str,
    score: int = 0,  # US-K Scoring: Announce updated score
    related_topics: list[str] | None = None,
    alternative_techniques: list[str] | None = None,
) -> dict[str, Any]:
    provider = "Groq AI" if _groq_enabled() else "Rule-based tutor"
    return {
        "course_id": activity["course_id"],
        "activity_no": activity["activity_no"],
        "title": activity["title"],
        "activity_text": _activity_text(activity),
        "status": activity["status"],
        "step_no": step_no,
        "progress_status": progress_status,
        "question": question,
        "message": f"[{provider}] {message}",
        "score": score,
        "related_topics": related_topics or [],
        "alternative_techniques": alternative_techniques or [],
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
                    learning_objectives TEXT NOT NULL DEFAULT '[]',
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
                ALTER TABLE activities
                ADD COLUMN IF NOT EXISTS learning_objectives TEXT NOT NULL DEFAULT '[]'
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
                    last_answer TEXT NOT NULL DEFAULT '',
                    history TEXT NOT NULL DEFAULT '[]',
                    score INTEGER NOT NULL DEFAULT 0,
                    achieved_objectives TEXT NOT NULL DEFAULT '[]',
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    UNIQUE (student_email, course_id, activity_no),
                    FOREIGN KEY (course_id, activity_no)
                        REFERENCES activities(course_id, activity_no)
                        ON DELETE CASCADE
                )
                """
            )
            # Migrate existing tables that may not have the scoring columns yet
            cursor.execute(
                """
                ALTER TABLE student_activity_progress
                ADD COLUMN IF NOT EXISTS score INTEGER NOT NULL DEFAULT 0
                """
            )
            cursor.execute(
                """
                ALTER TABLE student_activity_progress
                ADD COLUMN IF NOT EXISTS achieved_objectives TEXT NOT NULL DEFAULT '[]'
                """
            )
            cursor.execute(
                """
                ALTER TABLE student_activity_progress
                ADD COLUMN IF NOT EXISTS last_answer TEXT NOT NULL DEFAULT ''
                """
            )
            # US-K Scoring: Log every score change
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS score_logs (
                    log_id BIGSERIAL PRIMARY KEY,
                    student_email TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    activity_no INTEGER NOT NULL,
                    step_no INTEGER NOT NULL,
                    new_score INTEGER NOT NULL,
                    objective_text TEXT NOT NULL DEFAULT '',
                    event_type TEXT NOT NULL DEFAULT 'objective_achieved',
                    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            cursor.execute(
                """
                ALTER TABLE score_logs ADD COLUMN IF NOT EXISTS objective_text TEXT NOT NULL DEFAULT ''
                """
            )
            cursor.execute(
                """
                ALTER TABLE score_logs ADD COLUMN IF NOT EXISTS event_type TEXT NOT NULL DEFAULT 'objective_achieved'
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS manual_grading_events (
                    event_id BIGSERIAL PRIMARY KEY,
                    instructor_email TEXT NOT NULL,
                    student_email TEXT NOT NULL,
                    course_id TEXT NOT NULL,
                    activity_no INTEGER NOT NULL,
                    old_score INTEGER,
                    new_score INTEGER NOT NULL,
                    reason TEXT,
                    logged_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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
            [
                "Identify the project problem",
                "Describe target users",
                "Define success criteria",
            ],
        ),
        (
            2,
            "Requirements analysis",
            "ACTIVE",
            "Review the requirements analysis activity. Focus on identifying functional requirements, non-functional requirements, and unclear assumptions.",
            [
                "Distinguish functional requirements",
                "Distinguish non-functional requirements",
                "Identify unclear assumptions",
            ],
        ),
        (
            3,
            "Sprint planning",
            "ENDED",
            "Reflect on sprint planning by connecting backlog items to concrete tasks, owners, and acceptance criteria.",
            [
                "Connect backlog items to tasks",
                "Assign implementation ownership",
                "Write acceptance criteria",
            ],
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

            for activity_no, title, status, activity_text, learning_objectives in activities:
                cursor.execute(
                    """
                    INSERT INTO activities (
                        course_id,
                        activity_no,
                        title,
                        status,
                        activity_text,
                        learning_objectives
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (course_id, activity_no) DO UPDATE
                    SET title = EXCLUDED.title,
                        status = EXCLUDED.status,
                        activity_text = EXCLUDED.activity_text,
                        learning_objectives = EXCLUDED.learning_objectives
                    """,
                    (
                        course_id,
                        activity_no,
                        title,
                        status,
                        activity_text,
                        _encode_learning_objectives(learning_objectives),
                    ),
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

    if os.getenv("INCLASS_DEMO_AUTH", "1") == "1" and token.startswith("demo:"):
        _, email, *name_parts = token.split(":")
        clean_email = email.strip().lower()
        if not clean_email:
            raise AuthError("Demo token does not contain an email")
        return {
            "email": clean_email,
            "email_verified": True,
            "name": ":".join(name_parts).strip() or clean_email,
            "sub": f"demo-{clean_email}",
        }

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    if not client_id:
        raise AuthError("GOOGLE_CLIENT_ID is not configured")

    try:
        payload = id_token.verify_oauth2_token(token, requests.Request(), client_id, clock_skew_in_seconds=300)
    except ValueError as exc:
        raise AuthError(f"Invalid Google ID token: {exc}") from exc

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
    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, role, user_email
        )
        activities = [
            dict(activity)
            for (stored_course_id, _), activity in store["activities"].items()
            if stored_course_id.lower() == course_id_from_store.lower()
        ]
        activities.sort(key=lambda item: (item["activity_no"], item["title"].lower()))
        return [
            _activity_response(activity, include_objectives=role == "instructor")
            for activity in activities
        ]

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
                SELECT course_id, activity_no, title, activity_text, learning_objectives, status
                FROM activities
                WHERE LOWER(course_id) = LOWER(%s)
                ORDER BY activity_no ASC, LOWER(title) ASC, activity_id ASC
                """,
                (course_id_from_db,),
            )

            return [
                _activity_response(activity, include_objectives=role == "instructor")
                for activity in _fetch_all_as_dicts(cursor)
            ]


def list_courses(role: str, user_email: str) -> list[dict[str, Any]]:
    if _use_memory_store():
        store = _memory_store()
        access_key = "instructor_courses" if role == "instructor" else "student_courses"
        course_ids = store[access_key].get(user_email.strip().lower(), set())
        return sorted(
            [store["courses"][course_id] for course_id in course_ids],
            key=lambda item: (item["name"].lower(), item["course_id"].lower()),
        )

    if role == "instructor":
        access_table = "instructor_courses"
        email_column = "instructor_email"
    elif role == "student":
        access_table = "student_courses"
        email_column = "student_email"
    else:
        raise CourseAccessError("Unsupported course role")

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT courses.course_id, courses.name
                FROM courses
                INNER JOIN {access_table}
                    ON {access_table}.course_id = courses.course_id
                WHERE LOWER({access_table}.{email_column}) = LOWER(%s)
                ORDER BY LOWER(courses.name), LOWER(courses.course_id)
                """,
                (user_email,),
            )
            return _fetch_all_as_dicts(cursor)


def get_active_activity_for_student(
    course_id: str,
    activity_no: int,
    student_email: str,
) -> dict[str, Any]:
    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, "student", student_email
        )
        activity = _memory_load_activity(store, course_id_from_store, activity_no)
        _ensure_active_activity(activity)
        return _activity_response(activity, include_objectives=False)

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

            return _activity_response(activity, include_objectives=False)


_RELEVANCE_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "this", "that", "these", "those",
    "and", "or", "but", "if", "as", "it", "its", "their", "they", "we",
    "you", "i", "he", "she", "which", "who", "what", "how", "when",
}


def _word_set(text: str) -> set[str]:
    return {w for w in text.lower().split() if len(w) > 3 and w not in _RELEVANCE_STOP_WORDS}


def _word_overlap_ratio(a: str, b: str) -> float:
    wa, wb = _word_set(a), _word_set(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _is_answer_relevant(answer: str, activity: dict[str, Any]) -> bool:
    """Returns False if answer is off-topic, too short, keyword-stuffed, or a copy-paste."""
    words = answer.strip().split()

    if len(words) < 10:
        return False

    # Keyword stuffing: very low unique word ratio
    unique_ratio = len(set(w.lower() for w in words)) / len(words)
    if unique_ratio < 0.4:
        return False

    # Activity topic relevance
    activity_corpus = " ".join([
        activity.get("title", ""),
        _activity_text(activity),
        " ".join(_decode_learning_objectives(activity.get("learning_objectives"))),
    ])
    topic_overlap = _word_overlap_ratio(answer, activity_corpus)
    if topic_overlap < 0.08:
        return False

    return True


def _is_repeated_answer(answer: str, last_answer: str) -> bool:
    """Returns True if current answer is suspiciously similar to the previous accepted answer."""
    if not last_answer.strip():
        return False
    return _word_overlap_ratio(answer, last_answer) >= 0.75


_AI_GENERATED_PHRASES = [
    "keep this concept in mind", "key takeaway", "as you progress",
    "[groq ai]", "score:", "final score", "activity complete",
    "tutoring flow", "objective achieved", "mini_lesson",
]


def _is_ai_generated_text(answer: str) -> bool:
    """Detect if the student is submitting AI-generated tutor text as their own answer."""
    lower = answer.lower()
    return any(phrase in lower for phrase in _AI_GENERATED_PHRASES)


def _compute_answer_result(
    activity: dict[str, Any],
    progress: dict[str, Any],
    answer: str,
    achieved_objectives: list[int],
    current_score: int,
) -> dict[str, Any]:
    """Pure business logic for one tutoring answer. Returns new state; no I/O."""
    completed_step = progress["step_no"]
    max_steps = _max_steps_for_activity(activity)

    # Hard reject: student submitted AI-generated text
    if _is_ai_generated_text(answer):
        return {
            "next_step_no": completed_step,
            "next_status": "IN_PROGRESS",
            "next_question": progress.get("last_question") or _generate_tutoring_question(activity, completed_step),
            "message": "Please write your own answer. Do not copy text from the tutor's feedback.",
            "new_score": current_score,
            "achieved_objectives": list(achieved_objectives),
            "completed_step": completed_step,
            "obj_text": "",
            "should_log_score": False,
            "related_topics": [],
            "alternative_techniques": [],
        }

    ai_feedback = _ai_tutoring_feedback(
        activity=activity,
        progress=progress,
        answer=answer,
        achieved_objectives=achieved_objectives,
    )
    fallback_feedback = _fallback_tutoring_feedback(
        activity=activity,
        progress=progress,
        answer=answer,
    )
    tutoring_feedback = ai_feedback or fallback_feedback

    # Guard 1: repeated answer (fuzzy, backend — don't trust AI)
    last_answer = progress.get("last_answer", "")
    if tutoring_feedback["objective_achieved"] and _is_repeated_answer(answer, last_answer):
        tutoring_feedback = {
            "objective_achieved": False,
            "feedback": "Your answer is too similar to your previous response. Please explain this concept in your own words with new reasoning.",
            "next_question": progress.get("last_question") or _generate_tutoring_question(activity=activity, step_no=completed_step, previous_answer=None),
            "mini_lesson": "",
        }

    # Guard 2: relevance + AI self-review
    if tutoring_feedback["objective_achieved"]:
        locally_relevant = _is_answer_relevant(answer, activity)
        ai_relevant = _ai_verify_relevance(answer, activity) if locally_relevant else False
        if not locally_relevant or not ai_relevant:
            tutoring_feedback = {
                "objective_achieved": False,
                "feedback": "Your answer does not address this activity's topic. Please focus on the activity content and try again.",
                "next_question": _generate_tutoring_question(activity=activity, step_no=completed_step, previous_answer=None),
                "mini_lesson": "",
            }

    mini_lesson = ""
    obj_text = ""
    new_score = current_score
    new_achieved = list(achieved_objectives)
    should_log_score = False

    objective_achieved = tutoring_feedback["objective_achieved"]
    if objective_achieved and completed_step not in achieved_objectives:
        objectives = _decode_learning_objectives(activity.get("learning_objectives"))
        obj_text = objectives[completed_step] if completed_step < len(objectives) else ""
        new_achieved.append(completed_step)
        new_score += 1
        should_log_score = True
        mini_lesson = (
            tutoring_feedback["mini_lesson"]
            if tutoring_feedback["mini_lesson"]
            else _generate_mini_lesson(completed_step, obj_text)
        )

    next_step_no = completed_step + (1 if objective_achieved else 0)

    if new_score >= max_steps:
        next_status = "COMPLETED"
        next_question = None
        message = (
            f"Excellent work! You have covered all {max_steps} objectives. "
            f"Final score: {new_score}/{max_steps}. Activity complete."
        )
        if mini_lesson:
            message = f"{message} {mini_lesson}"
    elif next_step_no >= max_steps:
        next_status = "COMPLETED"
        next_question = None
        message = f"Activity complete. Score: {new_score}/{max_steps}."
        if mini_lesson:
            message = f"{message} {mini_lesson}"
    else:
        next_status = "IN_PROGRESS"
        next_question = (
            tutoring_feedback["next_question"]
            if tutoring_feedback["next_question"]
            else _generate_tutoring_question(
                activity=activity,
                step_no=next_step_no,
                previous_answer=answer,
            )
        )
        message = (
            tutoring_feedback["feedback"]
            if tutoring_feedback["feedback"]
            else f"Follow-up question generated. Score: {new_score}/{max_steps}."
        )
        if tutoring_feedback["feedback"]:
            message = f"{message} Score: {new_score}/{max_steps}."
        if mini_lesson:
            message = f"{message} {mini_lesson}"

    return {
        "next_step_no": next_step_no,
        "next_status": next_status,
        "next_question": next_question,
        "message": message,
        "new_score": new_score,
        "achieved_objectives": new_achieved,
        "completed_step": completed_step,
        "obj_text": obj_text,
        "should_log_score": should_log_score,
        "related_topics": tutoring_feedback.get("related_topics") or [],
        "alternative_techniques": tutoring_feedback.get("alternative_techniques") or [],
    }


def run_tutoring_turn(
    course_id: str,
    activity_no: int,
    student_email: str,
    answer: str | None = None,
) -> dict[str, Any]:
    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, "student", student_email
        )
        activity = _memory_load_activity(store, course_id_from_store, activity_no)
        _ensure_active_activity(activity)

        progress_key = (student_email.strip().lower(), course_id_from_store, activity_no)
        progress = store["progress"].get(progress_key)

        if progress is None:
            question = _generate_tutoring_question(activity, step_no=0)
            store["progress"][progress_key] = {
                "student_email": student_email.strip().lower(),
                "course_id": course_id_from_store,
                "activity_no": activity_no,
                "step_no": 0,
                "status": "IN_PROGRESS",
                "last_question": question,
                "history": "[]",
                "score": 0,
                "achieved_objectives": "[]",
            }
            return _tutoring_response(
                activity=activity,
                progress_status="IN_PROGRESS",
                step_no=0,
                question=question,
                message="Activity text is shown before the first tutor question",
                score=0,
            )

        if progress["status"] == "COMPLETED":
            return _tutoring_response(
                activity=activity,
                progress_status="COMPLETED",
                step_no=progress["step_no"],
                question=None,
                message="Tutoring flow is already completed",
                score=progress.get("score", 0),
            )

        if answer is None:
            return _tutoring_response(
                activity=activity,
                progress_status=progress["status"],
                step_no=progress["step_no"],
                question=progress["last_question"],
                message="Answer the current question to continue",
                score=progress.get("score", 0),
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

        achieved_objectives = _decode_achieved_objectives(progress)
        current_score = progress.get("score", 0)
        result = _compute_answer_result(activity, progress, cleaned_answer, achieved_objectives, current_score)

        if result["should_log_score"]:
            store["score_logs"].append(
                {
                    "student_email": student_email.strip().lower(),
                    "course_id": course_id_from_store,
                    "activity_no": activity_no,
                    "step_no": result["completed_step"],
                    "new_score": result["new_score"],
                    "objective_text": result["obj_text"],
                    "event_type": "objective_achieved",
                }
            )

        progress.update(
            {
                "step_no": result["next_step_no"],
                "status": result["next_status"],
                "last_question": result["next_question"],
                "last_answer": answer or "",
                "history": json.dumps(history),
                "score": result["new_score"],
                "achieved_objectives": json.dumps(result["achieved_objectives"]),
            }
        )
        return _tutoring_response(
            activity=activity,
            progress_status=result["next_status"],
            step_no=result["next_step_no"],
            question=result["next_question"],
            message=result["message"],
            score=result["new_score"],
            related_topics=result.get("related_topics"),
            alternative_techniques=result.get("alternative_techniques"),
        )

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
                        history,
                        score,
                        achieved_objectives
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        student_email,
                        course_id_from_db,
                        activity_no,
                        0,
                        "IN_PROGRESS",
                        question,
                        "[]",
                        0,
                        "[]",
                    ),
                )
                return _tutoring_response(
                    activity=activity,
                    progress_status="IN_PROGRESS",
                    step_no=0,
                    question=question,
                    message="Activity text is shown before the first tutor question",
                    score=0,
                )

            if progress["status"] == "COMPLETED":
                return _tutoring_response(
                    activity=activity,
                    progress_status="COMPLETED",
                    step_no=progress["step_no"],
                    question=None,
                    message="Tutoring flow is already completed",
                    score=progress.get("score", 0),
                )

            if answer is None:
                return _tutoring_response(
                    activity=activity,
                    progress_status=progress["status"],
                    step_no=progress["step_no"],
                    question=progress["last_question"],
                    message="Answer the current question to continue",
                    score=progress.get("score", 0),
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

            # --- US-K Scoring: Add +1 on first achievement / Prevent duplicate scoring ---
            achieved_objectives = _decode_achieved_objectives(progress)
            current_score = progress.get("score", 0)
            result = _compute_answer_result(activity, progress, cleaned_answer, achieved_objectives, current_score)

            if result["should_log_score"]:
                _log_score_change(
                    cursor=cursor,
                    student_email=student_email,
                    course_id=course_id_from_db,
                    activity_no=activity_no,
                    step_no=result["completed_step"],
                    new_score=result["new_score"],
                    objective_text=result["obj_text"],
                )

            cursor.execute(
                """
                UPDATE student_activity_progress
                SET step_no = %s,
                    status = %s,
                    last_question = %s,
                    last_answer = %s,
                    history = %s,
                    score = %s,
                    achieved_objectives = %s,
                    updated_at = NOW()
                WHERE LOWER(student_email) = LOWER(%s)
                  AND LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (
                    result["next_step_no"],
                    result["next_status"],
                    result["next_question"],
                    answer or "",
                    json.dumps(history),
                    result["new_score"],
                    json.dumps(result["achieved_objectives"]),
                    student_email,
                    course_id_from_db,
                    activity_no,
                ),
            )

            return _tutoring_response(
                activity=activity,
                progress_status=result["next_status"],
                step_no=result["next_step_no"],
                question=result["next_question"],
                message=result["message"],
                score=result["new_score"],
                related_topics=result.get("related_topics"),
                alternative_techniques=result.get("alternative_techniques"),
            )


def _update_activity_in_db(
    course_id: str,
    activity_no: int,
    updates: Dict[str, Any],
    role: str,
    user_email: str,
) -> Dict[str, Any]:
    allowed_fields = {"title", "status", "activity_text", "learning_objectives"}
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

    if "learning_objectives" in update_values:
        update_values["learning_objectives"] = _encode_learning_objectives(
            update_values["learning_objectives"]
        )

    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, role, user_email
        )
        activity = _memory_load_activity(store, course_id_from_store, activity_no)
        activity.update(update_values)
        store["activities"][(course_id_from_store, activity_no)] = activity
        return _activity_response(activity, include_objectives=True)

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
                RETURNING course_id, activity_no, title, activity_text, learning_objectives, status
                """,
                (*values, course_id_from_db, activity_no),
            )

            updated_activity = _fetch_one_as_dict(cursor)
            if updated_activity is None:
                raise ActivityAccessError("Activity was not found")

            return _activity_response(updated_activity, include_objectives=True)


def create_activity(
    course_id: str,
    activity_no: int,
    title: str,
    activity_text: str,
    learning_objectives: list[str],
    instructor_email: str,
) -> Dict[str, Any]:
    clean_title = title.strip()
    clean_activity_text = activity_text.strip()
    if activity_no <= 0:
        raise ActivityAccessError("Activity number must be positive")
    if not clean_title:
        raise ActivityAccessError("Activity title is required")
    if not clean_activity_text:
        raise ActivityAccessError("Activity text is required")

    encoded_objectives = _encode_learning_objectives(learning_objectives)

    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, "instructor", instructor_email
        )
        key = (course_id_from_store, activity_no)
        if key in store["activities"]:
            raise ActivityAccessError("Activity number already exists in this course")
        activity = {
            "course_id": course_id_from_store,
            "activity_no": activity_no,
            "title": clean_title,
            "activity_text": clean_activity_text,
            "learning_objectives": encoded_objectives,
            "status": "NOT_STARTED",
        }
        store["activities"][key] = activity
        return _activity_response(activity, include_objectives=True)

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role="instructor",
                user_email=instructor_email,
            )
            cursor.execute(
                """
                SELECT 1
                FROM activities
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            if cursor.fetchone() is not None:
                raise ActivityAccessError("Activity number already exists in this course")

            cursor.execute(
                """
                INSERT INTO activities (
                    course_id,
                    activity_no,
                    title,
                    activity_text,
                    learning_objectives,
                    status
                )
                VALUES (%s, %s, %s, %s, %s, 'NOT_STARTED')
                RETURNING course_id, activity_no, title, activity_text, learning_objectives, status
                """,
                (
                    course_id_from_db,
                    activity_no,
                    clean_title,
                    clean_activity_text,
                    encoded_objectives,
                ),
            )
            activity = _fetch_one_as_dict(cursor)
            if activity is None:
                raise ActivityAccessError("Activity could not be created")
            return _activity_response(activity, include_objectives=True)


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


def reset_activity(
    course_id: str,
    activity_no: int,
    instructor_email: str,
) -> Dict[str, Any]:
    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, "instructor", instructor_email
        )
        activity = _memory_load_activity(store, course_id_from_store, activity_no)
        store["score_logs"] = [
            log
            for log in store["score_logs"]
            if not (
                log["course_id"].lower() == course_id_from_store.lower()
                and log["activity_no"] == activity_no
            )
        ]
        store["manual_grading_events"] = [
            event
            for event in store["manual_grading_events"]
            if not (
                event["course_id"].lower() == course_id_from_store.lower()
                and event["activity_no"] == activity_no
            )
        ]
        store["progress"] = {
            key: progress
            for key, progress in store["progress"].items()
            if not (
                progress["course_id"].lower() == course_id_from_store.lower()
                and progress["activity_no"] == activity_no
            )
        }
        activity["status"] = "ENDED"
        store["activities"][(course_id_from_store, activity_no)] = activity
        return _activity_response(activity, include_objectives=True)

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role="instructor",
                user_email=instructor_email,
            )
            _load_activity(cursor, course_id_from_db, activity_no)

            cursor.execute(
                """
                DELETE FROM score_logs
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            cursor.execute(
                """
                DELETE FROM manual_grading_events
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            cursor.execute(
                """
                DELETE FROM student_activity_progress
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            cursor.execute(
                """
                UPDATE activities
                SET status = 'ENDED'
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                RETURNING course_id, activity_no, title, activity_text, learning_objectives, status
                """,
                (course_id_from_db, activity_no),
            )
            activity = _fetch_one_as_dict(cursor)
            if activity is None:
                raise ActivityAccessError("Activity was not found")
            return _activity_response(activity, include_objectives=True)


def manual_grade_activity(
    course_id: str,
    activity_no: int,
    student_email: str,
    score: int,
    instructor_email: str,
    reason: str | None = None,
) -> Dict[str, Any]:
    normalized_student_email = student_email.strip().lower()
    if not normalized_student_email:
        raise ActivityAccessError("Student email is required")

    if score < 0:
        raise ActivityAccessError("Score must be 0 or greater")

    clean_reason = reason.strip() if reason else None

    if _use_memory_store():
        store = _memory_store()
        course_id_from_store = _memory_validate_course_ownership(
            store, course_id, "instructor", instructor_email
        )
        _memory_validate_course_ownership(
            store, course_id_from_store, "student", normalized_student_email
        )
        activity = _memory_load_activity(store, course_id_from_store, activity_no)
        _ensure_activity_allows_scoring(activity)

        progress_key = (normalized_student_email, course_id_from_store, activity_no)
        progress = store["progress"].get(progress_key)
        old_score = progress.get("score") if progress else None
        if progress is None:
            initial_question = _generate_tutoring_question(activity, step_no=0)
            progress = {
                "student_email": normalized_student_email,
                "course_id": course_id_from_store,
                "activity_no": activity_no,
                "step_no": 0,
                "status": "IN_PROGRESS",
                "last_question": initial_question,
                "history": "[]",
                "score": score,
                "achieved_objectives": "[]",
            }
            store["progress"][progress_key] = progress
        else:
            progress["score"] = score

        store["score_logs"].append(
            {
                "student_email": normalized_student_email,
                "course_id": course_id_from_store,
                "activity_no": activity_no,
                "step_no": progress["step_no"],
                "new_score": score,
            }
        )
        store["manual_grading_events"].append(
            {
                "instructor_email": instructor_email,
                "student_email": normalized_student_email,
                "course_id": course_id_from_store,
                "activity_no": activity_no,
                "old_score": old_score,
                "new_score": score,
                "reason": clean_reason,
            }
        )
        return {
            "course_id": course_id_from_store,
            "activity_no": activity_no,
            "student_email": normalized_student_email,
            "score": score,
            "old_score": old_score,
            "graded_by": instructor_email,
        }

    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role="instructor",
                user_email=instructor_email,
            )
            _validate_course_ownership(
                cursor=cursor,
                course_id=course_id_from_db,
                role="student",
                user_email=normalized_student_email,
            )
            activity = _load_activity(cursor, course_id_from_db, activity_no)
            _ensure_activity_allows_scoring(activity)

            progress = _load_progress(
                cursor=cursor,
                course_id=course_id_from_db,
                activity_no=activity_no,
                student_email=normalized_student_email,
            )
            old_score = progress.get("score") if progress else None
            status = "COMPLETED" if score >= _max_steps_for_activity(activity) else "IN_PROGRESS"
            initial_question = _generate_tutoring_question(activity, step_no=0)

            cursor.execute(
                """
                INSERT INTO student_activity_progress (
                    student_email,
                    course_id,
                    activity_no,
                    step_no,
                    status,
                    last_question,
                    history,
                    score,
                    achieved_objectives,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (student_email, course_id, activity_no)
                DO UPDATE SET score = EXCLUDED.score,
                              updated_at = NOW()
                RETURNING student_email, course_id, activity_no, score
                """,
                (
                    normalized_student_email,
                    course_id_from_db,
                    activity_no,
                    progress["step_no"] if progress else 0,
                    progress["status"] if progress else status,
                    progress["last_question"] if progress else initial_question,
                    progress["history"] if progress else "[]",
                    score,
                    progress["achieved_objectives"] if progress else "[]",
                ),
            )
            graded_progress = _fetch_one_as_dict(cursor)
            if graded_progress is None:
                raise ActivityAccessError("Manual grade could not be saved")

            _log_score_change(
                cursor=cursor,
                student_email=normalized_student_email,
                course_id=course_id_from_db,
                activity_no=activity_no,
                step_no=progress["step_no"] if progress else 0,
                new_score=score,
            )
            _log_manual_grading_event(
                cursor=cursor,
                instructor_email=instructor_email,
                student_email=normalized_student_email,
                course_id=course_id_from_db,
                activity_no=activity_no,
                old_score=old_score,
                new_score=score,
                reason=clean_reason,
            )

            return {
                "course_id": graded_progress["course_id"],
                "activity_no": graded_progress["activity_no"],
                "student_email": graded_progress["student_email"],
                "score": graded_progress["score"],
                "old_score": old_score,
                "graded_by": instructor_email,
            }

def reset_activity(
    course_id: str,
    activity_no: int,
    instructor_email: str,
) -> Dict[str, Any]:
    with _db_connection() as connection:
        with connection.cursor() as cursor:
            course_id_from_db = _validate_course_ownership(
                cursor=cursor,
                course_id=course_id,
                role="instructor",
                user_email=instructor_email,
            )

            _load_activity(cursor, course_id_from_db, activity_no)

            cursor.execute(
                """
                DELETE FROM score_logs
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            deleted_score_logs = cursor.rowcount

            cursor.execute(
                """
                DELETE FROM student_activity_progress
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            deleted_student_progress = cursor.rowcount

            cursor.execute(
                """
                DELETE FROM manual_grading_events
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                """,
                (course_id_from_db, activity_no),
            )
            deleted_manual_grades = cursor.rowcount

            cursor.execute(
                """
                UPDATE activities
                SET status = 'ENDED'
                WHERE LOWER(course_id) = LOWER(%s)
                  AND activity_no = %s
                RETURNING course_id, activity_no, title, activity_text, status
                """,
                (course_id_from_db, activity_no),
            )

            reset_activity_row = _fetch_one_as_dict(cursor)
            if reset_activity_row is None:
                raise ActivityAccessError("Activity could not be reset")

            return {
                "course_id": reset_activity_row["course_id"],
                "activity_no": reset_activity_row["activity_no"],
                "title": reset_activity_row["title"],
                "status": reset_activity_row["status"],
                "deleted_score_logs": deleted_score_logs,
                "deleted_student_progress": deleted_student_progress,
                "deleted_manual_grades": deleted_manual_grades,
            }
