# InClass LLM Platform

## Project Overview
InClass LLM Platform is a classroom activity management and tutoring system developed for the Software Engineering course project.

The platform allows instructors to manage classroom activities while students participate in guided tutoring sessions during active class periods. The system supports objective-based scoring, student progress tracking, and instructor-controlled activity management.

The project is developed using FastAPI and PostgreSQL/Supabase following Scrum methodology with GitHub and ClickUp process tracking.

---

## Features

### Instructor Features
- Instructor authentication
- Course authorization control
- List assigned courses
- Create activities
- Update activities
- Start / End activities
- Manual grading support
- Reset activity functionality
- Export score support

### Student Features
- Student authentication
- Access only ACTIVE activities
- Guided tutoring interaction
- One-question-at-a-time tutoring flow
- Objective-based scoring
- Student progress tracking
- Automatic activity completion detection

### System Features
- Server-side authorization
- PostgreSQL/Supabase persistence
- Score logging with metadata
- Duplicate objective prevention
- Activity state management
- Scrum and GitHub traceability workflow

---

## Tech Stack

- Python
- FastAPI
- PostgreSQL
- Supabase
- GitHub
- ClickUp

---

## Project Structure

```text
app/
 ├── main.py
 ├── services.py
 └── __init__.py

tests/
instructor_tests/
requirements.txt
README.md
```

---

## Installation

### Clone Repository

```bash
git clone <repo-url>
cd SE-term-project
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Run Application

```bash
uvicorn app.main:app --reload
```

---

## Required Environment Variables

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
DATABASE_URL=
```

---

## API Features

### Instructor APIs
- instructorLogin
- listMyCourses
- listActivities
- createActivity
- updateActivity
- startActivity
- endActivity
- exportScores
- resetActivity

### Student APIs
- studentLogin
- getActivity
- logScore

---

## Scrum Workflow

The project follows a 2-sprint Scrum process including:
- Sprint Planning
- Daily Scrum
- Sprint Review
- Sprint Retrospective
- Scope Change Logs
- GitHub Pull Requests and Reviews

---

## Contributors

- Baran Bulduk
- Berk Özkan
- Yiğit Ahmet Turan
- Göktuğ Çakır
- Kaan Dinç

---

## Course Information

Software Engineering Course Project  
MEF University  
2026
