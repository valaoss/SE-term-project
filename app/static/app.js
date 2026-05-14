const state = {
  role: "instructor",
  token: "",
  courses: [],
  activities: [],
  selectedCourse: "",
  selectedActivityNo: null,
};

(function enforceAuth() {
  const storedToken = localStorage.getItem('inclass_token');
  const storedRole  = localStorage.getItem('inclass_role');
  if (!storedToken) {
    window.location.replace('/login');
    return;
  }
  state.token = storedToken;
  if (storedRole === 'instructor' || storedRole === 'student') {
    state.role = storedRole;
  }
  const tokenEl = document.getElementById('token');
  if (tokenEl) tokenEl.value = storedToken;
})();

function signOut() {
  localStorage.removeItem('inclass_token');
  localStorage.removeItem('inclass_role');
  window.location.replace('/login');
}

const el = (id) => document.getElementById(id);

function setApiState(message, type = "") {
  const node = el("apiState");
  node.textContent = message;
  node.className = `pill ${type}`;
}

function showError(error) {
  const message = error?.message || String(error);
  setApiState(message, "ended");
  console.error(error);
}

function authHeaders() {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${state.token}`,
  };
}

async function request(path, options = {}) {
  setApiState("API working", "pending");
  const response = await fetch(path, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) {
      localStorage.removeItem('inclass_token');
      localStorage.removeItem('inclass_role');
      window.location.replace('/login');
      return;
    }
    const detail = payload.detail || response.statusText;
    setApiState(detail, "ended");
    throw new Error(detail);
  }
  setApiState("API ready", "active");
  return payload;
}

async function loadHealth() {
  const response = await fetch("/api/health");
  const health = await response.json();
  el("aiState").textContent = health.ai_enabled
    ? `Tutor: Groq AI (${health.ai_model})`
    : "Tutor: rule-based fallback";
}

function setRole(role) {
  state.role = role;
  el("email").value = role === "instructor" ? "instructor@mef.edu.tr" : "student@mef.edu.tr";
  state.token = "";
  el("token").value = "";
  el("sessionState").textContent = "Not signed in";
  el("workspaceTitle").textContent = role === "instructor" ? "Instructor workspace" : "Student workspace";
  el("workspaceSubtitle").textContent =
    role === "instructor"
      ? "Manage activities, state, scoring, and exceptions."
      : "Work only on active activities with one tutoring question at a time.";
  el("instructorView").classList.toggle("hidden", role !== "instructor");
  el("studentView").classList.toggle("hidden", role !== "student");
}

async function loginWithDemoToken() {
  const email = el("email").value.trim();
  state.token = `demo:${email}:${email.split("@")[0]}`;
  el("token").value = state.token;
  await verifySession();
}

async function verifySession() {
  state.token = el("token").value.trim();
  if (!state.token) {
    state.token = `demo:${el("email").value.trim()}:${el("email").value.split("@")[0]}`;
    el("token").value = state.token;
  }
  const endpoint =
    state.role === "instructor" ? "/auth/google/verify-instructor" : "/auth/google/verify-student";
  const session = await request(endpoint, { method: "POST", body: "{}" });
  el("sessionState").textContent = `${session.role}: ${session.email}`;
  await loadCourses();
}

async function loadCourses() {
  const courses = await request(`/${state.role}/courses`);
  state.courses = courses;
  const select = el("courseSelect");
  select.innerHTML = "";
  for (const course of courses) {
    const option = document.createElement("option");
    option.value = course.course_id;
    option.textContent = `${course.course_id} - ${course.name}`;
    select.append(option);
  }
  state.selectedCourse = courses[0]?.course_id || "";
  select.value = state.selectedCourse;
  if (!state.selectedCourse) {
    state.activities = [];
    renderEmptyActivities();
    setApiState("No assigned course", "ended");
    return;
  }
  await loadActivities();
}

async function loadActivities() {
  if (!state.selectedCourse) {
    renderEmptyActivities();
    return;
  }
  state.activities = await request(`/${state.role}/courses/${state.selectedCourse}/activities`);
  state.selectedActivityNo = state.activities[0]?.activity_no || null;
  renderActivities();
}

function renderEmptyActivities() {
  const target = state.role === "instructor" ? el("activityList") : el("studentActivityList");
  target.innerHTML = '<div class="empty-state">No activities loaded.</div>';
}

function statusClass(status) {
  if (status === "ACTIVE") return "active";
  if (status === "ENDED") return "ended";
  return "pending";
}

function renderActivities() {
  const target = state.role === "instructor" ? el("activityList") : el("studentActivityList");
  target.innerHTML = "";
  if (!state.activities.length) {
    renderEmptyActivities();
    return;
  }
  for (const activity of state.activities) {
    const card = document.createElement("article");
    card.className = `activity-card ${activity.activity_no === state.selectedActivityNo ? "selected" : ""}`;
    card.innerHTML = `
      <h4>#${activity.activity_no} ${activity.title}</h4>
      <p>${activity.activity_text || ""}</p>
      <div class="meta-row">
        <span class="pill ${statusClass(activity.status)}">${activity.status}</span>
        ${
          activity.learning_objectives
            ? `<span class="pill">${activity.learning_objectives.length} objectives</span>`
            : ""
        }
      </div>
    `;
    card.addEventListener("click", () => selectActivity(activity.activity_no));
    target.append(card);
  }
  fillActivityForm();
}

function selectedActivity() {
  return state.activities.find((activity) => activity.activity_no === state.selectedActivityNo);
}

function selectActivity(activityNo) {
  state.selectedActivityNo = activityNo;
  renderActivities();
}

function fillActivityForm() {
  const activity = selectedActivity();
  if (!activity || state.role !== "instructor") {
    return;
  }
  el("activityNo").value = activity.activity_no;
  el("activityTitle").value = activity.title;
  el("activityText").value = activity.activity_text || "";
  el("objectives").value = (activity.learning_objectives || []).join("\n");
}

function activityPayload() {
  return {
    activity_no: Number(el("activityNo").value),
    title: el("activityTitle").value.trim(),
    activity_text: el("activityText").value.trim(),
    learning_objectives: el("objectives").value.split("\n").map((line) => line.trim()).filter(Boolean),
  };
}

async function createActivity() {
  await request(`/instructor/courses/${state.selectedCourse}/activities`, {
    method: "POST",
    body: JSON.stringify(activityPayload()),
  });
  await loadActivities();
}

async function updateActivity() {
  if (!state.selectedActivityNo) {
    setApiState("Select an activity first", "ended");
    return;
  }
  const payload = activityPayload();
  delete payload.activity_no;
  await request(`/instructor/courses/${state.selectedCourse}/activities/${state.selectedActivityNo}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  await loadActivities();
}

async function transitionActivity(action) {
  if (!state.selectedActivityNo) {
    setApiState("Select an activity first", "ended");
    return;
  }
  await request(`/instructor/courses/${state.selectedCourse}/activities/${state.selectedActivityNo}/${action}`, {
    method: "POST",
    body: "{}",
  });
  await loadActivities();
}

async function submitGrade() {
  if (!state.selectedActivityNo) {
    setApiState("Select an activity first", "ended");
    return;
  }
  await request(`/instructor/courses/${state.selectedCourse}/activities/${state.selectedActivityNo}/manual-grade`, {
    method: "POST",
    body: JSON.stringify({
      student_email: el("gradeStudent").value.trim(),
      score: Number(el("gradeScore").value),
      reason: el("gradeReason").value.trim(),
    }),
  });
}

function appendMessage(kind, text) {
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.textContent = text;
  el("chatLog").append(node);
  node.scrollIntoView({ block: "end" });
}

async function openStudentActivity() {
  const activity = selectedActivity();
  if (!activity) {
    setApiState("Select an active activity first", "ended");
    return;
  }
  const fullActivity = await request(
    `/student/courses/${state.selectedCourse}/activities/${activity.activity_no}`
  );
  el("activityTextBox").textContent = fullActivity.activity_text;
  el("chatLog").innerHTML = "";
  const turn = await request(
    `/student/courses/${state.selectedCourse}/activities/${activity.activity_no}/tutoring-turn`,
    { method: "POST", body: "{}" }
  );
  appendTutorTurn(turn);
}

function appendTutorTurn(turn) {
  if (turn.message) appendMessage("system", turn.message);
  if (turn.question) appendMessage("question", turn.question);
  const topics = turn.related_topics || [];
  const techniques = turn.alternative_techniques || [];
  if (topics.length || techniques.length) {
    appendSuggestions(topics, techniques);
  }
}

function appendSuggestions(topics, techniques) {
  const box = document.createElement("div");
  box.className = "suggestions-box";

  if (topics.length) {
    const label = document.createElement("div");
    label.className = "suggestions-label";
    label.textContent = "Related Topics";
    box.append(label);
    const row = document.createElement("div");
    row.className = "chip-row";
    topics.forEach((t) => {
      const chip = document.createElement("button");
      chip.className = "chip chip-topic";
      chip.textContent = t;
      chip.type = "button";
      chip.addEventListener("click", () => {
        el("studentAnswer").value = `Regarding "${t}": `;
        el("studentAnswer").focus();
        el("studentAnswer").setSelectionRange(9999, 9999);
      });
      row.append(chip);
    });
    box.append(row);
  }

  if (techniques.length) {
    const label = document.createElement("div");
    label.className = "suggestions-label";
    label.textContent = "Alternative Techniques";
    box.append(label);
    const row = document.createElement("div");
    row.className = "chip-row";
    techniques.forEach((t) => {
      const chip = document.createElement("button");
      chip.className = "chip chip-technique";
      chip.textContent = t;
      chip.type = "button";
      chip.addEventListener("click", () => {
        el("studentAnswer").value = `I would ${t.toLowerCase()}: `;
        el("studentAnswer").focus();
        el("studentAnswer").setSelectionRange(9999, 9999);
      });
      row.append(chip);
    });
    box.append(row);
  }

  el("chatLog").append(box);
  box.scrollIntoView({ block: "end" });
}

async function sendAnswer() {
  if (!state.selectedActivityNo) {
    setApiState("Open an active activity first", "ended");
    return;
  }
  const answer = el("studentAnswer").value.trim();
  if (!answer) {
    return;
  }
  appendMessage("student", answer);
  el("studentAnswer").value = "";
  const turn = await request(
    `/student/courses/${state.selectedCourse}/activities/${state.selectedActivityNo}/tutoring-turn`,
    { method: "POST", body: JSON.stringify({ answer }) }
  );
  appendTutorTurn(turn);
}

function bindEvents() {
  el("role").addEventListener("change", (event) => setRole(event.target.value));
  el("courseSelect").addEventListener("change", async (event) => {
    state.selectedCourse = event.target.value;
    await loadActivities();
  });
  el("demoLogin").addEventListener("click", () => loginWithDemoToken().catch(showError));
  el("verifyLogin").addEventListener("click", () => verifySession().catch(showError));
  el("refreshData").addEventListener("click", () => loadCourses().catch(showError));
  el("createActivity").addEventListener("click", () => createActivity().catch(showError));
  el("updateActivity").addEventListener("click", () => updateActivity().catch(showError));
  el("startActivity").addEventListener("click", () => transitionActivity("start").catch(showError));
  el("endActivity").addEventListener("click", () => transitionActivity("end").catch(showError));
  el("resetActivity").addEventListener("click", () => transitionActivity("reset").catch(showError));
  el("submitGrade").addEventListener("click", () => submitGrade().catch(showError));
  el("openActivity").addEventListener("click", () => openStudentActivity().catch(showError));
  el("sendAnswer").addEventListener("click", () => sendAnswer().catch(showError));
}

bindEvents();
const _initialRole = localStorage.getItem('inclass_role') || 'instructor';
setRole(_initialRole);
loadHealth().catch(showError);
