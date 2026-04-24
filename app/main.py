import os
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Import the logic we just wrote in services.py
from app.services import verify_google_token

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "InClass LLM Backend is running!"}

# NEW: The verification endpoint Claude asked for
@app.post("/auth/google/verify")
async def verify_google(token: str = Header(...)):
    # Call the service function
    result = verify_google_token(token)
    
    if not result["ok"]:
        raise HTTPException(status_code=401, detail=result["error"])
    
    # University Check
    if not result["email"].endswith("@mef.edu.tr"):
        raise HTTPException(status_code=403, detail="Only @mef.edu.tr emails are allowed.")
    
    return {
        "status": "success",
        "user": result
    }