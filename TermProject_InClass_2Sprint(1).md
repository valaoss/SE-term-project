# Software Engineering Term Project - InClass Platform (2 Sprint Edition)

## 1. Fixed Inputs and Constraints

This document defines the full project process for student teams.

- Project duration: 2 sprints, each sprint is 2 weeks.
- Team velocity input: 35 SP per sprint.
- Required implementation language: Python.
- Required database: PostgreSQL.
- Product goal:
  Build and demo a working system where instructors manage activities, students work only on ACTIVE activities, and objective based scoring is logged correctly.
- GitHub repository is mandatory.
- ClickUp is mandatory for all process management.
- Authentication and authorization rule:
  Authentication may use Google Sign-In or equivalent federated auth.
  Backend must verify identity for protected requests.
  Backend must enforce role and course authorization server-side.
- LLM prompt and student responsibilities:
  The student prompt is provided by the instructor and defines the baseline target behavior.
  Teams must implement the core tutoring flow described in the provided student prompt.
  Teams may revise or improve the prompt for better performance, but they must document all prompt changes.
  Any prompt revision must preserve the core tutoring flow, scoring logic, and activity terminology.
  If teams revise the baseline prompt, they must submit a `PROMPT_CHANGES.md` file describing the changes, rationale, and expected effect.
- Activity generation scope:
  LLM-based activity generation from slides is out of scope for this term project.
  Teams are responsible for storing, managing, and delivering instructor-provided activities only.
  The activity generator prompt may be used as reference material, but implementing an automated generator is not required.
- No separate permanent Scrum Master or Product Owner role.
  In each sprint, one developer must take the facilitation and backlog ownership responsibilities.
  In Sprint 2, this must be a different person from Sprint 1.

## 2. Required Product Deliverables

The final system must include the following product deliverables:

- Instructor authentication with Google Sign-In or equivalent federated auth.
- Student authentication with Google Sign-In or equivalent federated auth.
- Backend identity verification and server-side role/course authorization for protected actions.
- Instructor course access limited to assigned courses only.
- Instructor activity management:
  create, update, start, end, list, and reset activity.
- Student activity access control:
  students can access only authorized and ACTIVE activities.
- Student tutoring flow:
  show the activity text first, ask one question at a time, guide with follow-up questions, and keep responses in English using activity terminology.
- Objective-based scoring:
  first achievement of an objective adds exactly +1, repeated achievement does not add score again, and all score changes are logged with metadata.
- Short mini-lesson behavior:
  after a point is earned for an objective, the system immediately announces the updated score and gives a short academic mini-lesson for that objective.
- Activity completion behavior:
  when all objectives are covered, the system celebrates and stops.
- Instructor manual grading for exceptional cases.
- PostgreSQL-backed persistence for users, course access, activities, student progress, and score logs.

## 3. Product Backlog (Not Ordered)

Important:
- Stories below are intentionally not ordered.
- Teams must decide priority order in Sprint Planning.
- Initial SP values are estimates.
- Teams must re-estimate with Planning Poker in each Sprint Planning.
- Each story is end-to-end delivery:
  database change + backend + frontend + test evidence.

### US-A (3 SP)
Story:
As an instructor, I want to sign in with Google Sign-In or equivalent federated auth so that I can use instructor functions securely.

Acceptance criteria:
- Valid federated sign-in returns successful authentication.
- Identity not mapped to an instructor account returns a clear error.
- Backend verifies identity before allowing instructor functions.

### US-B (3 SP)
Story:
As a student, I want to sign in with Google Sign-In or equivalent federated auth so that I can use student functions securely.

Acceptance criteria:
- Valid federated sign-in returns successful authentication.
- Identity not mapped to a student account returns a clear error.
- Backend verifies identity before allowing student functions.

### US-C (5 SP)
Story:
As a system, I want to map authenticated users to platform roles and course access so that only authorized users can use protected resources.

Acceptance criteria:
- Authenticated instructor identities are mapped to the correct instructor records.
- Authenticated student identities are mapped to the correct student records.
- Server-side authorization rejects authenticated but unauthorized access.
- Authorization is enforced in the backend, not only in the frontend.

### US-D (3 SP)
Story:
As an instructor, I want to list only my assigned courses so that I cannot access unrelated courses.

Acceptance criteria:
- Only assigned courses are returned.
- Access to non-assigned courses is rejected.
- Another instructor's course is never visible.

### US-E (3 SP)
Story:
As an instructor, I want to list activities in a selected course so that I can choose which activity to manage.

Acceptance criteria:
- Course activity list is returned correctly.
- Each item includes at least activity number and activity status.
- List order is deterministic (for example by activity number ascending).

### US-F (5 SP)
Story:
As an instructor, I want to create a new activity with text and objectives so that I can prepare class activities.

Acceptance criteria:
- Activity can be created with required fields.
- Missing required fields returns a clear error.
- Duplicate activity number in the same course is rejected.

### US-G (5 SP)
Story:
As an instructor, I want to update activity text and objectives so that I can revise content before class.

Acceptance criteria:
- Only allowed fields can be updated.
- Empty patch is rejected.
- Non-existent activity returns a clear error.

### US-H (5 SP)
Story:
As an instructor, I want to start and end an activity so that class timing is controlled by the instructor.

Acceptance criteria:
- Start sets state to ACTIVE.
- End sets state to ENDED.
- ENDED activity cannot accept new score logs.

### US-I (5 SP)
Story:
As a student, I want to access activity content only when the activity is ACTIVE so that class rules are enforced.

Acceptance criteria:
- NOT_STARTED activity is not accessible.
- ACTIVE activity returns the activity text without exposing learning objectives.
- ENDED activity is not accessible.
- Non-enrolled or unauthorized student access is rejected.

### US-J (8 SP)
Story:
As a student, I want to submit answers and receive the next guiding question so that I can progress step by step.

Acceptance criteria:
- The first tutoring response after fetching the activity shows the activity text and asks exactly one question.
- System returns one next guidance question per step.
- Follow-up questions steer the student toward the next objective instead of revealing answers directly.
- Student progress is stored per student per activity.
- Student-facing tutoring responses are in English and use activity terminology.
- If activity is ENDED, flow cannot continue.

### US-K (8 SP)
Story:
As a system, I want to increase score when an objective is achieved so that grading is objective based.

Acceptance criteria:
- First achievement of an objective adds +1 score.
- Repeating the same objective does not add score again.
- Every score change is logged with student, course, activity, score, and metadata.
- When an objective is achieved, the updated score is announced immediately.
- The system gives a short academic mini-lesson only after that objective earns a point.
- When all objectives are covered, the system celebrates and stops.

### US-L (5 SP)
Story:
As an instructor, I want to enter manual grades for exceptions so that classroom disruptions can be handled.

Acceptance criteria:
- Instructor can submit manual grade for a student in a specific activity.
- Manual grade is logged with a manual grading event.
- Unauthorized instructor cannot submit manual grade.

### US-M (5 SP)
Story:
As an instructor, I want to reset an activity by deleting all student scores and closing the activity so that incorrect runs can be cleaned safely.

Acceptance criteria:
- All score records for that course and activity are deleted.
- Activity state is set to ENDED after reset.
- New score logging is blocked after reset.

## 4. Scrum Process Requirements

Teams must run full Scrum ceremonies in both sprints.

Mandatory artifacts and events:
- Product Goal file.
- Sprint Goal file for Sprint 1 and Sprint 2.
- Sprint Planning for Sprint 1 and Sprint 2.
- Sprint Backlog for Sprint 1 and Sprint 2 (must be task level).
- Sprint Board in ClickUp.
- Daily Scrum records:
  minimum 2 per sprint.
- Sprint Review records for Sprint 1 and Sprint 2.
- Sprint Retrospective records for Sprint 1 and Sprint 2.
- Definition of Done (DoD) file.
- Prompt change log file (`PROMPT_CHANGES.md`), if the baseline prompt is revised.
- Burndown chart for each sprint.
- Backlog refinement:
  at least 1 refinement record per sprint.

Daily timing rule:
- Daily Scrum evidence cannot be from Sprint Day 1 or Sprint Day 10.
- For a 10 working day sprint, accepted daily evidence window is Day 3 to Day 8.

## 5. ClickUp and Board Evidence Rules

All process work must be tracked in ClickUp.

Required board evidence:
- Sprint 1 baseline board screenshot after Sprint Planning.
- Sprint 2 baseline board screenshot after Sprint Planning.
- At least 2 post-daily board screenshots in Sprint 1.
- At least 2 post-daily board screenshots in Sprint 2.
- Sprint 1 final board screenshot on Review day.
- Sprint 2 final board screenshot on Review day.

Each screenshot must provide enough visible information to verify board timing and task progress.

Minimum required visible information:
- date and time, or another clear timestamp indicator,
- board status columns or an equivalent workflow view,
- task IDs and titles, or equivalent task identifiers and names.

The exact ClickUp layout does not need to match a specific template as long as the required information is clearly visible.

## 6. Scope Change Log Requirements

Scope Change Log is mandatory for both sprints.

The log must include every sprint backlog change after planning.
This includes:
- task add,
- task remove,
- task split,
- task re-estimate,
- task status transition.

Status transition logging is mandatory.
Example:
- TASK-24 changed from In Progress to Done at 2026-03-21 16:40.

Minimum required information:
- timestamp,
- sprint,
- item ID,
- change type,
- from state,
- to state,
- reason,
- impact on Sprint Goal,
- decision owner,
- ClickUp task link,
- related GitHub link (issue, PR, or commit if available).

Column names do not need to match these labels exactly.
Equivalent field names are acceptable as long as the submitted log clearly includes the required information.

## 7. GitHub and Identity Rules

- GitHub is mandatory.
- Teams must include the exact GitHub repository URL in the submission package.
- Teams must grant repository access to both instructors:
  `bekmezcii@mef.edu.tr` and `duranf@mef.edu.tr` (at least read access).
- Commit ownership rule:
  A commit is counted for the GitHub username that made the commit.
- All students must use school email in GitHub account and commit identity.
- Contribution evidence is evaluated per person.
- Required per person evidence:
  commits, PRs, code reviews, meeting attendance.

## 8. Timeline Consistency and Audit

All timeline evidence is audited from project start date to demo date.

Sources that will be cross-checked:
- GitHub commit timestamps,
- GitHub PR and review timestamps,
- ClickUp task history,
- ClickUp task activity log,
- submitted evidence file timestamps.

WARNING:
GITHUB COMMIT DATES, CLICKUP TASK HISTORY DATES, AND CLICKUP TASK ACTIVITY LOG DATES WILL BE CROSS-CHECKED.
DO NOT TRY TO COMPLETE THE PROJECT BY BULK UPLOADING IN THE LAST TWO DAYS.

Penalty rule:
- If submitted evidence is inconsistent with ClickUp history or activity logs, penalty is -50 points.
- If evidence file is missing, that item is graded as zero.

## 9. Submission Format (No Narrative Report)

There is no single narrative report requirement.
Evidence must be submitted as separate files.

Rules:
- Every evidence item must be a separate file.
- File names must be meaningful and match the evidence content.
- All files must be submitted in one ZIP package.
- The ZIP package must include a separate folder named `source_code` that contains the full source code.
- The ZIP package must include a file named `REPO_INFO.txt` with:
  GitHub repository URL, default branch name, and sprint release tags (`sprint-1`, `sprint-2`).
- If the baseline prompt is revised, the ZIP package must include `PROMPT_CHANGES.md`.

Suggested filename format:
- TEAMID_SPRINT_EVIDENCE_YYYY-MM-DD.ext

Examples:
- G03_S1_SPRINT_BACKLOG_2026-03-18.csv
- G03_S1_DAILY1_BOARD_2026-03-20.png
- G03_S2_SCOPE_CHANGE_LOG_2026-04-04.csv
- G03_GLOBAL_CLICKUP_TASK_HISTORY_2026-04-10.csv
- G03_GLOBAL_CLICKUP_ACTIVITY_LOG_2026-04-10.csv

## 10. Rubric (200 Points Total)

The rubric uses 200 raw points to provide grading granularity across process, evidence, implementation, and demo performance.
Final project percentage is calculated as:
earned points / 200 * 100

Final demo is exactly 50 points.

| Evidence ID | Evidence item | Points |
|---|---|---:|
| E01 | Product Goal file | 5 |
| E02 | Product Backlog file with initial SP | 5 |
| E03 | Planning Poker re-estimate evidence for Sprint 1 | 5 |
| E04 | Planning Poker re-estimate evidence for Sprint 2 | 5 |
| E05 | Sprint Goal file for Sprint 1 | 3 |
| E06 | Sprint Goal file for Sprint 2 | 3 |
| E07 | Sprint Planning record for Sprint 1 | 4 |
| E08 | Sprint Planning record for Sprint 2 | 4 |
| E09 | Sprint Backlog task breakdown for Sprint 1 | 5 |
| E10 | Sprint Backlog task breakdown for Sprint 2 | 5 |
| E11 | ClickUp board baseline screenshot for Sprint 1 | 2 |
| E12 | ClickUp board baseline screenshot for Sprint 2 | 2 |
| E13 | Daily Scrum records for Sprint 1 (min 2) | 5 |
| E14 | Daily Scrum records for Sprint 2 (min 2) | 5 |
| E15 | Post-daily board screenshots for Sprint 1 (min 2) | 5 |
| E16 | Post-daily board screenshots for Sprint 2 (min 2) | 5 |
| E17 | Sprint Review record and evidence for Sprint 1 | 5 |
| E18 | Sprint Review record and evidence for Sprint 2 | 5 |
| E19 | Sprint Retrospective record and action list for Sprint 1 | 5 |
| E20 | Sprint Retrospective record and action list for Sprint 2 | 5 |
| E21 | Burndown chart for Sprint 1 | 5 |
| E22 | Burndown chart for Sprint 2 | 5 |
| E23 | Scope Change Log for Sprint 1 | 6 |
| E24 | Scope Change Log for Sprint 2 | 6 |
| E25 | ClickUp Task History export (project start to demo date) | 6 |
| E26 | ClickUp Task Activity Log export (project start to demo date) | 6 |
| E27 | Acceptance criteria and tutoring-flow test evidence matrix | 12 |
| E28 | GitHub commit traceability evidence (story-task-commit mapping) | 6 |
| E29 | GitHub PR evidence | 5 |
| E30 | GitHub code review evidence | 5 |
| E31 | Meeting attendance evidence per person | 5 |
| E32 | Git tags evidence for sprint releases (`sprint-1`, `sprint-2`) | 4 |
| E33 | ZIP submission structure compliance | 1 |
| E34 | Final demo | 50 |

Total: 200 points.

## 11. LLM Budget and Model Usage Note

- Each group will receive 1 dollar OpenRouter credit.
- This is enough for initial development trials with oss-120-b.
- For demo, teams may use DeepSeek if outcomes are better.
- To reduce cost, run early manual tests in OpenRouter chat using free models first.
