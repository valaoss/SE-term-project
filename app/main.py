from typing import Annotated, Optional, Dict, Any

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.services import (
    AuthError,
    InstructorUser,
    StudentUser,
    instructor_google_login,
    map_to_instructor_account,
    map_to_student_account,
    student_google_login,
    verify_google_token,
)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GoogleLoginRequest(BaseModel):
    token: str


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