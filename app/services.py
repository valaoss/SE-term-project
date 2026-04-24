import os
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from supabase import create_client, Client

# Initialize Supabase Client
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

def verify_google_token(token: str) -> dict:
    try:
        idinfo = id_token.verify_oauth2_token(
            token, 
            google_requests.Request(), 
            os.getenv("GOOGLE_CLIENT_ID")
        )

        user_email = idinfo["email"]
        google_id = idinfo["sub"]
        full_name = idinfo.get("name", "")

        # Check if user exists in 'instructors' or 'students'
        # For simplicity, let's try to find or create in students first
        # You can later add logic to differentiate roles
        user_data = {
            "full_name": full_name,
            "email": user_email,
            "google_id": google_id
        }

        # Example: Upsert (Update if exists, Insert if not)
        response = supabase.table("students").upsert(user_data, on_conflict="email").execute()

        return {
            "ok": True,
            "email": user_email,
            "google_id": google_id,
            "name": full_name,
            "db_record": response.data
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}