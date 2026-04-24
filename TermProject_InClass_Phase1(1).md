# Software Engineering Term Project -- InClass LLM Platform (API-based)

**Course:** Software Engineering  
**Implementation language:** **Python**  
Note: You may also implement in TypeScript (TS) only with prior approval from the instructor. You must obtain permission before starting any TS development.
**Backend storage:** **Supabase (PostgreSQL)**  
**Work mode:** Group project (team size as announced in class)  
**Version control & Scrum evidence:** GitHub logs (Issues, Projects, Milestones, commit history)

---

## Key Dates (Deadlines)

- **Phase 1 deadline:** **March 13, 2026** %35
- **Phase 2 deadline:** **April 03, 2026** %35
- **Phase 3 deadline:** **April 24, 2026** %30

> Exact demo slots (time & room) will be announced in advance.

---

## 1. Project Overview (Short Description)

InClass LLM Platform is a classroom activity system designed to support **in-class, instructor-controlled learning activities** at scale.

At a high level:

- An **instructor** prepares an activity for a specific course, and **opens/closes** the activity during class.
- A **student** can access the activity **only while it is active**, interacts with the system during class, and earns points when the system detects that the student has achieved a learning objective.
- The system maintains course/activity data and produces **exportable score reports** for the instructor.

This project is **not** a CustomGPT build. Instead, it is a **standard API-based application** implemented in Python. Data persistence is handled via **Supabase (PostgreSQL)**.
Note: You may also implement in TypeScript (TS) only with prior approval from the instructor. You must obtain permission before starting any TS development.

---

## 2. User Scenarios (Instructor & Student)

### 2.1 Instructor Scenario (Plan -> Run -> Close -> Export)

1. **Before class**, the instructor signs in and selects the course they are responsible for.
2. The instructor reviews existing activities for that course and prepares a new activity for the day:
   - writes the activity text shown to students,
   - defines the activity's learning objectives,
   - optionally revises the activity before class.
3. **At the start of class**, the instructor **opens** the activity. From this moment on, students can access it.
4. During class, the instructor may monitor overall progress and handle classroom exceptions (e.g., a student's device fails). In such cases, the instructor may assign a score manually when needed.
5. **At the end of class**, the instructor **closes** the activity. After this moment, students can no longer access the activity.
6. After class, the instructor exports score reports for the course/activity for grading and record keeping.
7. If an activity was started by mistake, the instructor can reset that activity and (optionally) clear its score records according to instructor policy.

### 2.2 Student Scenario (Access -> Work -> Earn Points During ACTIVE Only)

1. The student signs in and (if required) sets/changes their password according to the project rules for the current phase.
2. Before the instructor opens the activity, the student cannot access the activity and receives a "not started yet" response.
3. Once the instructor opens the activity, the student can access the activity text and begins working during class.
4. The system conducts a guided interaction. The student improves answers from vague to specific and technically grounded.
5. **Scoring rule (strict):**
   - Whenever the system detects that the student has **achieved a learning objective**, the score is recorded **immediately**.
   - When **all learning objectives are completed**, the system stops the activity interaction for that student.
   - **After the instructor closes the activity, no score can be recorded under any condition.**
6. After class, the student cannot continue the activity.

---

## 3. API Contract (Exact Signatures)

### 3.1 Non-negotiable API Signature Policy

- **Penalty:** For each API endpoint whose signature does not match the provided contract, **-5 points** will be applied, **even if your implementation works.**
- Your implementation must remain compatible with the instructor's test scripts.
### 3.1.1 Authentication Model (Required)
There is no token, session, JWT, or cookie. Every protected request must include `email` and `password`.
All API functions and HTTP endpoints must validate credentials on every call.

### 3.2 Endpoints and Brief Descriptions

This section lists each required endpoint and includes a short description of what it does.
**These are the exact signatures.**

#### Student APIs

**Student auth APIs**
- def studentLogin(email: str, password: str) -> dict: ...

**Student password APIs**
- def changeStudentPassword(email: str, password: str, new_password: str, old_password: str) -> dict: ...
- def setStudentPassword(email: str, password: str) -> dict: ...
**NOTE: The setStudentPassword works if the student has no password in the database (first run)**


**Main student APIs**
- def getActivity(email: str, password: str, course_id: str, activity_no: int) -> dict: ...
- def logScore(email: str, password: str, course_id: str, activity_no: int, score: float, meta: str | None = None) -> dict: ...

#### Instructor APIs

**Instructor auth APIs**
- def instructorLogin(email: str, password: str) -> dict: ...

**Instructor password APIs**

- def changeInstructorPassword(email: str, password: str, old_password: str, new_password: str) -> dict: ...
- def setInstructorPassword(email: str, password: str | None = None) -> dict: ...
**NOTE: The setInstructorPassword works if the instructor has no password in the database (first run)**

**Main APIs for Instructor**
- def listMyCourses(email: str, password: str) -> dict: ...
- def listActivities(email: str, password: str, course_id: str) -> dict: ...
- def createActivity(email: str, password: str, course_id: str, activity_text: str, learning_objectives: list[str], activity_no_optional: int | None = None) -> dict[str, object]: ...
- def updateActivity(email: str, password: str, course_id: str, activity_no: int, patch: dict) -> dict: ...
- def startActivity(email: str, password: str, course_id: str, activity_no: int) -> dict: ...
- def endActivity(email: str, password: str, course_id: str, activity_no: int) -> dict: ...

**The following API produces csv document**
- def exportScores(email: str, password: str, course_id: str, activity_no: int) -> dict: ...

**The following API deletes all the scores related to the given activity_no**
- def resetActivity(email: str, password: str, course_id: str, activity_no: int) -> dict: ...

**The following API resets a student's password**
- def resetStudentPassword(email: str, password: str, course_id: str, student_email: str, new_password: str) -> dict: ...

---

## 4. Phase 1 Requirements (What You Must Deliver for Phase 1)

### 4.1 Scope

For **Phase 1**, you must implement:

- The complete Phase 1 endpoint set defined in the API Contract.
- A working Supabase-backed persistence layer (designing the Supabase schema is part of the work).
- Full support for the Instructor and Student scenarios described above.
- The system must be implemented in **Python**.
- Note: You may also implement in TypeScript (TS) only with prior approval from the instructor. You must obtain permission before starting any TS development.

### 4.2 Project Development Rules

Groups that do not follow these rules will receive **-20 points**.

#### Required repository structure
Your repository must include (at minimum):

```text
(repo root)/
  app/
    __init__.py
    main.py
    services.py
  tests/                 # your own tests (you can add anything here)
  instructor_tests/      # reserved for instructor/assistant grading tests (do not modify)
    .keep
  requirements.txt OR pyproject.toml
  .gitignore
  README.md
```

Rules:
- Do not delete, rename, or modify `instructor_tests/`. During grading, the instructor will place their tests under this folder.
- Put your own tests under `tests/` (not under `instructor_tests/`).

#### Service layer vs HTTP layer (tests vs real API)
You must implement the Phase 1 functions in `app/services.py`. Instructor tests will call these functions directly.
Your FastAPI routes in `app/main.py` must call the corresponding functions in `app/services.py` so the project is publishable as a real API.

#### Runnable FastAPI entrypoint (importable)
Your project must expose a FastAPI application at `app/main.py` so the instructor tests can import it without starting a server.

Minimal example (`app/main.py`):

```python
import os
from fastapi import FastAPI

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
DATABASE_URL = os.environ["DATABASE_URL"]

app = FastAPI()

@app.post("/student/get-activity")
def getActivity(*, email: str, password: str, course_id: str, activity_no: int) -> dict[str, object]:
    return {"ok": True}

@app.post("/instructor/list-my-courses")
def listMyCourses(*, email: str, password: str) -> dict[str, object]:
    return {"ok": True}
```

Notes:
- Do not hardcode any Supabase credentials. Read them from environment variables.
- Avoid heavy side effects at import time (do not run migrations or long network calls when the module is imported).
- Instructor tests will import the app like this: `from app.main import app` and will call it via TestClient (no server startup).

#### Required environment variable names (Supabase)
Your code must read these exact environment variables (names are fixed):
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `DATABASE_URL`

#### Git hygiene (secrets must not be committed)
Your repository must not contain committed secrets or local environments.

Minimum `.gitignore` entries:
```text
.env
.env.*
.venv/
__pycache__/
*.pyc
```

### 4.3 Phase 1 Deliverables (Submission)

You must submit **all of the following** to Blackboard (BB):

1. **Phase 1 Result Report** (internship report format, adapted):
   - Project short introduction (1/2 page)
   - What was implemented in this phase
   - Product Backlog items created
   - Sprints executed (Sprint Baclog, Sprint goals, scope, dates, Definiton of Done)
   - Who did what (team contribution summary)
   - Test results (include outputs/screenshots)
   - Code delivered per sprint (link to tag/release per sprint)
2. **Source code** (ZIP will be submitted to BB)
3. **GitHub logs** (exported evidence for Scrum evaluation; ZIP will be submitted to BB)

---

## 5. Demo Rules (Applies to Each Phase Demo)

- Demos are conducted **as a group**.
- Any student who is late at the exact scheduled time receives **-10 points**.
- Any student who does not participate in the demo will receive **0 points** as the final grade for this phase of the project.
- The demo will run on the assistant's computer.
- In Supabase at least 2 instructor and 2 students for 2 different courses will be ready to test.
- During the demo:
  - The team must log in to GitHub on the assistant's computer.
  - The team must log in to the project's Supabase account on the assistant's computer.
  - The assistant will pull the repository, collect logs, and inspect the Supabase database state.
  - The assistant will run the instructor's test scripts.
  - A test report will appear immediately and the team's functional score will be determined on the spot.
  - The assistant will upload feedback to Blackboard after the demo.
- Maximum demo duration: **15 minutes**.
- Demo schedule (group, time, room) will be announced in advance.

---

## 6. Grading for Phase 1

- **Functional correctness (tests): 60 points**
- **Report: 10 points**
- **Scrum usage on GitHub (Github log-based evaluation): 35 points**

### Penalty recap 
- **-5 points** for each API endpoint whose signature does not match the provided contract.
- **-20 points** if the Project Development Rules are not followed.
- **-10 points** for being late to the demo.
- **0 points** for the Phase 1 grade if a student does not participate in the demo.
- **0 points** for the report if it is submitted after the deadline.

---

## 7. FAQ (Read Before Asking)

**Q: Where do we put our own tests?**  
A: Put all your tests under `tests/`. Do not put your tests under `instructor_tests/`.

**Q: What is `instructor_tests/` for?**  
A: It is reserved for the instructor's grading tests. Do not delete, rename, or modify it.

**Q: Do we need to start a server (uvicorn) for the demo?**  
A: No. Instructor tests will import `app` from `app/main.py` and call it with TestClient.

**Q: Can we change the file path or name of `app/main.py`?**  
A: No. The path must stay `app/main.py` because the tests import from there.

**Q: Can we use a different web framework (Flask, Django, etc.)?**  
A: No. You must expose a FastAPI app in `app/main.py`.

**Q: Do we have to include our dependencies?**  
A: Yes. You must include either `requirements.txt` or `pyproject.toml`.

**Q: Can we commit `.env` or `.venv/` to the repo?**  
A: No. Those must be ignored by git.

**Q: We uploaded the report 5 minutes late. What happens?**  
A: You had weeks to upload the report. Any group that does not submit the report on time receives **zero points** from the report evaluation.

---

*This document is Phase 1 oriented. Phase 2 and Phase 3 requirements will be released later in the semester.*
