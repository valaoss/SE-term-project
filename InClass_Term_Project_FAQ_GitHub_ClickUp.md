# Student FAQ for the InClass Platform Term Project

_GitHub + ClickUp guidance written in a student-question / instructor-answer format_

> **Quick note from the instructor:** The hard rules come from the project brief. Where the brief is silent, this FAQ gives recommended team practice. So when you see a sentence like **"I strongly recommend"**, treat it as the safest professional way to run your project, not as an extra hidden requirement.
>
> Most important advice: use one GitHub Organization, one team repository, one ClickUp workspace/space/list structure, and keep your evidence consistent from day one.


## 1. Project Basics and Team Setup

**Question:** What tools are mandatory for this project?

**Answer:** GitHub is mandatory for the repository, and ClickUp is mandatory for process management. The implementation language must be Python, and the database must be PostgreSQL. Do not redesign the assignment around a different stack.

**Question:** Can we change the required technology stack?

**Answer:** No. Python and PostgreSQL are fixed requirements. You may choose supporting libraries and frameworks, but you should not replace the required language or database.

**Question:** Can we skip Scrum and just show the final product?

**Answer:** No. This project is graded on both product and process. You must run Scrum ceremonies in both sprints and submit evidence for planning, backlog work, dailies, reviews, retrospectives, burndown charts, and scope change logs.

**Question:** Can the same person act as the facilitator in both sprints?

**Answer:** No. The brief says there is no permanent Scrum Master or Product Owner. In each sprint, one developer takes facilitation and backlog ownership responsibilities, and the Sprint 2 person must be different from Sprint 1.

**Question:** Can we change the baseline LLM prompt?

**Answer:** Yes, but carefully. You may improve the prompt, but you must preserve the core tutoring flow, scoring logic, and activity terminology. If you revise the prompt, you must submit a PROMPT_CHANGES.md file that explains what changed, why it changed, and what effect you expect.

**Question:** Do we need to build automatic activity generation from slides?

**Answer:** No. That is out of scope. You are only responsible for storing, managing, and delivering instructor-provided activities.


## 2. GitHub FAQ

**Question:** Do we have to use GitHub Organization for our team?

**Answer:** Strictly speaking, no. The hard requirement is that your team must use GitHub and submit the exact repository URL, while giving both instructors at least read access. However, I strongly recommend using a GitHub Organization. It is cleaner, more stable, easier to manage, and more professional than keeping the repository under one student's personal account.

**Question:** If GitHub Organization is not mandatory, why do you still want us to use it?

**Answer:** Because it solves practical team problems before they become grading problems. Repository ownership stays with the team instead of one student, member access is easier to manage, instructor access is clearer, and the project remains organized even if one teammate becomes inactive. A shared repository under one student's account can work, but it is the weaker setup.

**Question:** What is the best GitHub setup for this course?

**Answer:** Create one GitHub Organization for the team, create one main repository inside it, add all teammates with their own accounts, and give the instructors read access. Then run your normal workflow with branches, pull requests, reviews, tags, and issue or task references.

**Question:** Can we keep the repository private?

**Answer:** Yes, that is usually fine in practice, as long as both instructors can access it and the exact repository URL is included in the submission package. A private repository without instructor access is not acceptable.

**Question:** Do all students need their own GitHub accounts?

**Answer:** Absolutely yes. Contribution evidence is evaluated per person. If multiple people use one account, you make your own evidence weak, confusing, and possibly unacceptable.

**Question:** Which email should we use in GitHub and in commit identity?

**Answer:** Use your school email in the GitHub account and in commit identity. The brief is explicit about this. Do not commit with random personal addresses if you want your work to be attributed correctly.

**Question:** What counts as contribution evidence for each student?

**Answer:** At minimum: commits, pull requests, code reviews, and meeting attendance. In other words, every student should leave a visible trace in both GitHub and the team process.

**Question:** Do we need pull requests and code reviews, or are commits enough?

**Answer:** You need pull request evidence and code review evidence as separate graded items, so commits alone are not enough. Use PRs properly, and review each other's work in GitHub instead of only talking in WhatsApp or Discord.

**Question:** How should we connect GitHub work to stories and tasks?

**Answer:** Use a traceable workflow. Reference story IDs, task IDs, or clear task names in branch names, commit messages, PR titles, and descriptions. When someone reviews your submission later, they should be able to move from backlog item to task to commit to PR without guessing.

**Question:** Do we need release tags?

**Answer:** Yes. Your REPO_INFO.txt must include the sprint release tags sprint-1 and sprint-2. Create them on time, not at the last minute.

**Question:** Can we upload everything to GitHub in the last two days if the code already exists locally?

**Answer:** Do not do that. The brief clearly warns that GitHub commit dates, ClickUp task history dates, ClickUp task activity dates, and evidence timestamps will be cross-checked. Bulk uploading at the end is exactly the kind of behavior that triggers audit concerns and penalties.

**Question:** Who must be added to the repository?

**Answer:** Both instructors must be added with at least read access: bekmezcii@mef.edu.tr and duranf@mef.edu.tr. Do this early, test it early, and do not wait for the submission night.


## 3. ClickUp and Scrum FAQ

**Question:** Is ClickUp really mandatory if we already track work somewhere else?

**Answer:** Yes. ClickUp is mandatory for all process management. You may use other tools for team communication if you want, but your graded process evidence must come from ClickUp.

**Question:** What exactly must be tracked in ClickUp?

**Answer:** All process work. That includes your Sprint Board, Sprint Backlog at task level, task status changes, planning outcomes, daily progress, review evidence, retrospective evidence, and scope change history.

**Question:** How detailed should our Sprint Backlog be?

**Answer:** Task level. A sprint backlog that contains only big user stories is too shallow. Break work down into implementable, testable tasks that can move visibly on the board.

**Question:** What should be visible in board screenshots?

**Answer:** A clear timestamp or time indicator, board status columns or equivalent workflow view, and task IDs plus task titles or equivalent identifiers. If I cannot verify timing and progress from the screenshot, the screenshot is weak evidence.

**Question:** Which board screenshots are required?

**Answer:** You need a Sprint 1 baseline board screenshot after Sprint Planning, a Sprint 2 baseline board screenshot after Sprint Planning, at least two post-daily board screenshots in Sprint 1, at least two post-daily board screenshots in Sprint 2, and a final board screenshot for each sprint on Review day.

**Question:** How many Daily Scrum records do we need?

**Answer:** At least two per sprint. Also remember the timing rule: daily evidence cannot be from Sprint Day 1 or Sprint Day 10. In a ten-working-day sprint, accepted daily evidence must come from Day 3 to Day 8.

**Question:** What is the Scope Change Log, and how serious is it?

**Answer:** It is mandatory, and it is serious. After Sprint Planning, every backlog change must be logged. That includes adding tasks, removing tasks, splitting tasks, re-estimating tasks, and even status transitions. Yes, status transition logging is also mandatory.

**Question:** What should a Scope Change Log entry contain?

**Answer:** At minimum: timestamp, sprint, item ID, change type, from state, to state, reason, impact on Sprint Goal, decision owner, ClickUp task link, and related GitHub link when available. Equivalent column names are fine, but the information itself must be there.

**Question:** Can we keep a very simple board with only To Do, Doing, and Done?

**Answer:** You can, if it still supports clear evidence and makes status transitions auditable. However, in practice I recommend a slightly richer workflow such as Backlog, To Do, In Progress, In Review, and Done, because it gives you cleaner screenshots and better traceability.

**Question:** What is the safest way to manage ClickUp during the project?

**Answer:** Update tasks continuously, not theatrically. Move statuses when work actually changes, attach useful descriptions, keep task titles specific, and link relevant GitHub work. A board that evolves naturally is easy to defend in an audit.


## 4. Evidence, Submission, and Audit FAQ

**Question:** What does timeline consistency mean for this course?

**Answer:** It means your story about the project must match your digital evidence. GitHub timestamps, PR dates, review dates, ClickUp history, ClickUp activity logs, and submitted file timestamps should support the same timeline.

**Question:** What happens if our evidence is inconsistent?

**Answer:** The brief states a penalty of minus 50 points if submitted evidence is inconsistent with ClickUp history or activity logs. Also, if an evidence file is missing, that item is graded as zero. So inconsistency and missing files are both expensive mistakes.

**Question:** Do we submit one big report?

**Answer:** No. There is no single narrative report requirement. Evidence must be submitted as separate files inside one ZIP package.

**Question:** What must be inside the ZIP package?

**Answer:** At minimum, meaningful evidence files, a separate folder named source_code containing the full source code, and a file named REPO_INFO.txt with the repository URL, default branch name, and sprint release tags. If you revised the baseline prompt, include PROMPT_CHANGES.md as well.

**Question:** Do filenames matter?

**Answer:** Yes. The brief says file names must be meaningful and must match the evidence content. Good naming is not decoration; it is part of making your submission auditable.

**Question:** What should REPO_INFO.txt include?

**Answer:** The exact GitHub repository URL, the default branch name, and the sprint release tags sprint-1 and sprint-2.

**Question:** What kind of product behavior is non-negotiable in the system itself?

**Answer:** Students should only access authorized and ACTIVE activities, the tutoring flow should show the activity first and then ask one question at a time, scoring must add exactly plus one only on the first achievement of each objective, repeated achievement must not add points again, and every score change must be logged with metadata.

**Question:** Do students see the learning objectives directly?

**Answer:** No. The acceptance criteria say the student can access the activity text without exposing learning objectives. Your tutoring flow should guide the student toward objectives rather than revealing them directly.

**Question:** Can we ignore testing evidence if the demo works?

**Answer:** No. There is a graded item for acceptance criteria and tutoring-flow test evidence matrix. A working demo helps, but grading still expects structured evidence.

**Question:** What is your final practical advice before we start?

**Answer:** Set up GitHub Organization on day one, configure school-email commit identity for every teammate, create a clean ClickUp board on the same day, start moving real tasks immediately, use PRs and reviews from Sprint 1 onward, and collect evidence continuously. In this project, discipline is not extra work; discipline is part of the grade.


## Recommended Day-One Setup Checklist

- [ ] Create the GitHub Organization and the main team repository.

- [ ] Add every teammate with their own GitHub account and school-email commit identity.

- [ ] Add both instructors to the repository with at least read access.

- [ ] Create the ClickUp board, statuses, and initial sprint structure.

- [ ] Agree on naming rules for tasks, branches, commits, PRs, and evidence files.

- [ ] Start producing traceable evidence from the first real work session.


_Prepared from the course project brief and tailored to emphasize the recommended GitHub Organization workflow._
