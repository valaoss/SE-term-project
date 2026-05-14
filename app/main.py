import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()
from typing import Annotated, Optional, Dict, Any, NoReturn

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.services import (
    ActivityAccessError,
    AuthError,
    CourseAccessError,
    CourseNotFoundError,
    DatabaseConfigError,
    EnglishResponseError,
    InstructorUser,
    StudentUser,
    create_activity,
    get_active_activity_for_student,
    initialize_activity_schema,
    instructor_google_login,
    list_activities,
    list_courses,
    manual_grade_activity,
    map_to_instructor_account,
    map_to_student_account,
    tutoring_provider_status,
    reset_activity,
    run_tutoring_turn,
    seed_demo_activity_data,
    student_google_login,
    update_activity,
    verify_google_token,
)

app = FastAPI()
logger = logging.getLogger(__name__)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class GoogleLoginRequest(BaseModel):
    token: str


class ActivityResponse(BaseModel):
    course_id: str
    activity_no: int
    title: str
    activity_text: Optional[str] = None
    status: str


class CourseResponse(BaseModel):
    course_id: str
    name: str


class InstructorActivityResponse(ActivityResponse):
    learning_objectives: list[str] = []


class StudentActivityAccessResponse(BaseModel):
    course_id: str
    activity_no: int
    title: str
    activity_text: str
    status: str


class TutoringTurnRequest(BaseModel):
    answer: Optional[str] = None


class TutoringTurnResponse(BaseModel):
    course_id: str
    activity_no: int
    title: str
    activity_text: str
    status: str
    step_no: int
    progress_status: str
    question: Optional[str] = None
    message: str
    score: int = 0  # US-K Scoring: Announce updated score
    related_topics: list[str] = []
    alternative_techniques: list[str] = []


class ManualGradeRequest(BaseModel):
    student_email: str
    score: int
    reason: Optional[str] = None


class ManualGradeResponse(BaseModel):
    course_id: str
    activity_no: int
    student_email: str
    score: int
    old_score: Optional[int] = None
    graded_by: str


class ActivityCreateRequest(BaseModel):
    activity_no: int
    title: str
    activity_text: str
    learning_objectives: list[str]


class ActivityUpdateRequest(BaseModel):
    title: Optional[str] = None
    activity_text: Optional[str] = None
    learning_objectives: Optional[list[str]] = None
    status: Optional[str] = None


@app.on_event("startup")
def create_activity_table() -> None:
    try:
        initialize_activity_schema()
        seed_demo_activity_data()
    except DatabaseConfigError as exc:
        logger.warning("Activity database was not initialized: %s", exc)


def _bearer_token(authorization: Optional[str]) -> str:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authorization header is required")

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(
            status_code=401,
            detail="Authorization header must be Bearer token",
        )

    return token


def require_instructor(
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
) -> InstructorUser:
    token = _bearer_token(authorization)
    try:
        payload = verify_google_token(token)
        return map_to_instructor_account(payload)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def require_student(
    authorization: Annotated[Optional[str], Header(alias="Authorization")] = None,
) -> StudentUser:
    token = _bearer_token(authorization)
    try:
        payload = verify_google_token(token)
        return map_to_student_account(payload)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.get("/")
def read_root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/login")
def login_page() -> FileResponse:
    return FileResponse(STATIC_DIR / "login.html")


@app.get("/api/health")
def health_check() -> Dict[str, Any]:
    return {"ok": True, **tutoring_provider_status()}


@app.post("/auth/google/instructor")
def google_instructor_login(request: GoogleLoginRequest) -> Dict[str, Any]:
    try:
        return instructor_google_login(request.token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/google/student")
def google_student_login(request: GoogleLoginRequest) -> Dict[str, Any]:
    try:
        return student_google_login(request.token)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


@app.post("/auth/google/verify-instructor")
def verify_instructor_token(
    instructor: Annotated[InstructorUser, Depends(require_instructor)]
) -> Dict[str, Any]:
    return {
        "ok": True,
        "role": "instructor",
        "email": instructor.email,
        "name": instructor.name,
    }


@app.post("/auth/google/verify-student")
def verify_student_token(
    student: Annotated[StudentUser, Depends(require_student)]
) -> Dict[str, Any]:
    return {
        "ok": True,
        "role": "student",
        "email": student.email,
        "name": student.name,
    }


@app.get(
    "/instructor/courses",
    response_model=list[CourseResponse],
)
def list_instructor_courses(
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> list[Dict[str, Any]]:
    try:
        return list_courses(role="instructor", user_email=instructor.email)
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/student/courses",
    response_model=list[CourseResponse],
)
def list_student_courses(
    student: Annotated[StudentUser, Depends(require_student)],
) -> list[Dict[str, Any]]:
    try:
        return list_courses(role="student", user_email=student.email)
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/student/courses/{course_id}/activities",
    response_model=list[ActivityResponse],
)
def list_student_activities(
    course_id: str,
    student: Annotated[StudentUser, Depends(require_student)],
) -> list[Dict[str, Any]]:
    try:
        return list_activities(
            course_id=course_id,
            role="student",
            user_email=student.email,
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/student/courses/{course_id}/activities/{activity_no}",
    response_model=StudentActivityAccessResponse,
)
def get_student_activity(
    course_id: str,
    activity_no: int,
    student: Annotated[StudentUser, Depends(require_student)],
) -> Dict[str, Any]:
    try:
        return get_active_activity_for_student(
            course_id=course_id,
            activity_no=activity_no,
            student_email=student.email,
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ActivityAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/student/courses/{course_id}/activities/{activity_no}/tutoring-turn",
    response_model=TutoringTurnResponse,
)
def post_student_tutoring_turn(
    course_id: str,
    activity_no: int,
    request: TutoringTurnRequest,
    student: Annotated[StudentUser, Depends(require_student)],
) -> Dict[str, Any]:
    try:
        return run_tutoring_turn(
            course_id=course_id,
            activity_no=activity_no,
            student_email=student.email,
            answer=request.answer,
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ActivityAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except EnglishResponseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get(
    "/instructor/courses/{course_id}/activities",
    response_model=list[InstructorActivityResponse],
)
def list_instructor_activities(
    course_id: str,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> list[Dict[str, Any]]:
    try:
        return list_activities(
            course_id=course_id,
            role="instructor",
            user_email=instructor.email,
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post(
    "/instructor/courses/{course_id}/activities",
    response_model=InstructorActivityResponse,
)
def create_instructor_activity(
    course_id: str,
    request: ActivityCreateRequest,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return create_activity(
            course_id=course_id,
            activity_no=request.activity_no,
            title=request.title,
            activity_text=request.activity_text,
            learning_objectives=request.learning_objectives,
            instructor_email=instructor.email,
        )
    except Exception as exc:
        _raise_activity_update_http_error(exc)


@app.patch(
    "/instructor/courses/{course_id}/activities/{activity_no}",
    response_model=InstructorActivityResponse,
)
def update_instructor_activity(
    course_id: str,
    activity_no: int,
    request: ActivityUpdateRequest,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return update_activity(
            course_id=course_id,
            activity_no=activity_no,
            updates=request.dict(exclude_unset=True),
            role="instructor",
            user_email=instructor.email,
        )
    except Exception as exc:
        _raise_activity_update_http_error(exc)


def _raise_activity_update_http_error(exc: Exception) -> NoReturn:
    if isinstance(exc, CourseNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, CourseAccessError):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ActivityAccessError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, DatabaseConfigError):
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post(
    "/instructor/courses/{course_id}/activities/{activity_no}/start",
    response_model=ActivityResponse,
)
def start_instructor_activity(
    course_id: str,
    activity_no: int,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return update_activity(
            course_id=course_id,
            activity_no=activity_no,
            updates={"status": "ACTIVE"},
            role="instructor",
            user_email=instructor.email,
        )
    except Exception as exc:
        _raise_activity_update_http_error(exc)


@app.post(
    "/instructor/courses/{course_id}/activities/{activity_no}/end",
    response_model=ActivityResponse,
)
def end_instructor_activity(
    course_id: str,
    activity_no: int,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return update_activity(
            course_id=course_id,
            activity_no=activity_no,
            updates={"status": "ENDED"},
            role="instructor",
            user_email=instructor.email,
        )
    except Exception as exc:
        _raise_activity_update_http_error(exc)


@app.post(
    "/instructor/courses/{course_id}/activities/{activity_no}/reset",
    response_model=InstructorActivityResponse,
)
def reset_instructor_activity(
    course_id: str,
    activity_no: int,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return reset_activity(
            course_id=course_id,
            activity_no=activity_no,
            instructor_email=instructor.email,
        )
    except Exception as exc:
        _raise_activity_update_http_error(exc)


@app.post(
    "/instructor/courses/{course_id}/activities/{activity_no}/manual-grade",
    response_model=ManualGradeResponse,
)
def post_manual_grade(
    course_id: str,
    activity_no: int,
    request: ManualGradeRequest,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return manual_grade_activity(
            course_id=course_id,
            activity_no=activity_no,
            student_email=request.student_email,
            score=request.score,
            instructor_email=instructor.email,
            reason=request.reason,
        )
    except Exception as exc:
        _raise_activity_update_http_error(exc)
