import os
import logging
from typing import Annotated, Optional, Dict, Any

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.services import (
    ActivityNotFoundError,
    AuthError,
    CourseAccessError,
    CourseNotFoundError,
    DatabaseConfigError,
    InstructorUser,
    StudentUser,
    create_activity,
    initialize_activity_schema,
    instructor_google_login,
    list_activities,
    map_to_instructor_account,
    map_to_student_account,
    seed_demo_activity_data,
    student_google_login,
    update_activity,
    verify_google_token,
)

app = FastAPI()
logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GoogleLoginRequest(BaseModel):
    token: str


class ActivityResponse(BaseModel):
    course_id: str
    activity_no: int
    title: str
    status: str


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


def _dev_mode_enabled() -> bool:
    return os.getenv("DEV_MODE", "").strip().lower() == "true"


def _dev_instructor_user() -> InstructorUser:
    email = os.getenv("DEV_INSTRUCTOR_EMAIL", "dev-instructor@example.com")
    return InstructorUser(
        email=email.strip().lower(),
        name="Dev Instructor",
        google_sub="dev-token",
    )


def _is_dev_instructor_token(
    credentials: Optional[HTTPAuthorizationCredentials],
) -> bool:
    return (
        _dev_mode_enabled()
        and credentials is not None
        and credentials.scheme.lower() == "bearer"
        and credentials.credentials.strip() == "dev-token"
    )


def require_instructor(
    credentials: Annotated[
        Optional[HTTPAuthorizationCredentials],
        Security(bearer_scheme),
    ] = None,
) -> InstructorUser:
    if _is_dev_instructor_token(credentials):
        return _dev_instructor_user()

    token = _bearer_token(
        f"{credentials.scheme} {credentials.credentials}" if credentials else None
    )

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
def read_root() -> Dict[str, bool]:
    return {"ok": True}


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
    "/instructor/courses/{course_id}/activities",
    response_model=list[ActivityResponse],
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


class CreateActivityRequest(BaseModel):
    activity_no: int
    title: str
    status: str


@app.post(
    "/instructor/courses/{course_id}/activities",
    response_model=ActivityResponse,
    status_code=201,
)
def create_instructor_activity(
    course_id: str,
    request: CreateActivityRequest,
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    try:
        return create_activity(
            course_id=course_id,
            activity_no=request.activity_no,
            title=request.title,
            status=request.status,
            role="instructor",
            user_email=instructor.email,
        )
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:          
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch(
    "/instructor/courses/{course_id}/activities/{activity_no}",
    response_model=ActivityResponse,
)
def update_instructor_activity(
    course_id: str,
    activity_no: int,
    request: Annotated[Dict[str, Any], Body()],
    instructor: Annotated[InstructorUser, Depends(require_instructor)],
) -> Dict[str, Any]:
    if not request:
        raise HTTPException(
            status_code=400,
            detail="Update request must include at least one editable field",
        )

    try:
        return update_activity(
            course_id=course_id,
            activity_no=activity_no,
            updates=request,
            role="instructor",
            user_email=instructor.email,
        )
    except ActivityNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CourseAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except DatabaseConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
