import os
from dataclasses import dataclass
from typing import Any

from google.auth.transport import requests
from google.oauth2 import id_token
from supabase import create_client, Client

# --- NEDEN EKLENDİ? ---
# Supabase veritabanı bağlantısını kurmak için senin eklediğin kısım.
supabase_url: str = os.getenv("SUPABASE_URL", "")
supabase_key: str = os.getenv("SUPABASE_KEY", "")
supabase: Client | None = None

if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)
# ----------------------

class AuthError(ValueError):
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

    # --- NEDEN EKLENDİ? ---
    # Eğitmen başarıyla giriş yaptığında, senin görevin gereği onu Supabase'deki
    # 'instructors' tablosuna kaydediyoruz. Zaten varsa bilgilerini güncelliyoruz (upsert).
    if supabase:
        user_data = {
            "email": instructor.email,
            "full_name": instructor.name,
            "google_id": instructor.google_sub
        }
        supabase.table("instructors").upsert(user_data, on_conflict="email").execute()
    # ----------------------

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

    # --- NEDEN EKLENDİ? ---
    # Öğrenci başarıyla giriş yaptığında, senin görevin gereği onu Supabase'deki
    # 'students' tablosuna kaydediyoruz.
    if supabase:
        user_data = {
            "email": student.email,
            "full_name": student.name,
            "google_id": student.google_sub
        }
        supabase.table("students").upsert(user_data, on_conflict="email").execute()
    # ----------------------

    return {
        "ok": True,
        "role": "student",
        "email": student.email,
        "name": student.name,
        "google_sub": student.google_sub,
    }