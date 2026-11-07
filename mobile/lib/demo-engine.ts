// Demo engine: a fully client-side simulated ARTHUR backend used when the
// app cannot reach a real server (offline demo mode). It mirrors the shapes
// of lib/api.ts so screens work unchanged.

import type {
  AgentStatus,
  Approval,
  ChatReply,
  Project,
  StatusResponse,
  Task,
} from "./api";
import {
  askBrain,
  buildSystemPrompt,
  loadBrainConfig,
  parseBrainActions,
  type BrainConfig,
  type BrainMessage,
} from "./brain";

const now = () => new Date().toISOString();
const minutesAgo = (m: number) =>
  new Date(Date.now() - m * 60000).toISOString();

let nextProjectId = 3;
let nextTaskId = 104;
let nextApprovalId = 2;

const agents: AgentStatus[] = [
  { id: 1, name: "planner", kind: "planner", permission_level: 2, status: "idle" },
  { id: 2, name: "researcher", kind: "worker", permission_level: 1, status: "idle" },
  { id: 3, name: "builder", kind: "worker", permission_level: 1, status: "idle" },
  { id: 4, name: "reviewer", kind: "reviewer", permission_level: 2, status: "idle" },
];

function mkTask(
  projectId: number,
  title: string,
  agent: string,
  state: string,
  criteria: string,
): Task {
  return {
    id: nextTaskId++,
    project_id: projectId,
    title,
    agent,
    deps: "[]",
    state,
    attempts: state === "COMPLETED" ? 1 : 0,
    max_attempts: 3,
    checkpoint: "{}",
    result: state === "COMPLETED" ? JSON.stringify({ summary: "done" }) : null,
    error: null,
    success_criteria: criteria,
    steps: "[]",
    next_retry_at: null,
    created_at: minutesAgo(90),
    updated_at: now(),
  };
}

const projects: Project[] = [
  {
    id: 1,
    name: "weekend-coding-project",
    description: "Plan a weekend coding project",
    status: "active",
    completion_conditions: JSON.stringify([
      "Project idea chosen",
      "Tech stack decided",
      "Milestones broken down",
    ]),
    created_at: minutesAgo(90),
    updated_at: now(),
  },
  {
    id: 2,
    name: "morning-routine-reset",
    description: "Design a better morning routine",
    status: "completed",
    completion_conditions: JSON.stringify([
      "Routine drafted",
      "Habit stack defined",
    ]),
    created_at: minutesAgo(60 * 26),
    updated_at: minutesAgo(60 * 24),
  },
];

const tasks: Task[] = [
  mkTask(1, "Choose the project idea", "planner", "COMPLETED", "One clear idea picked"),
  mkTask(1, "Decide the tech stack", "researcher", "COMPLETED", "Stack listed with reasons"),
  mkTask(1, "Break down milestones", "planner", "RUNNING", "Milestones with owners"),
  mkTask(1, "Draft the build checklist", "builder", "QUEUED", "Checklist saved"),
  mkTask(2, "Draft the routine", "planner", "COMPLETED", "Routine drafted"),
  mkTask(2, "Define the habit stack", "reviewer", "COMPLETED", "Habits ordered"),
];

const approvals: Approval[] = [
  {
    id: 1,
    kind: "tool_access",
    subject: "builder requests network access for research",
    detail: JSON.stringify({ tool: "web_search", scope: "read-only" }),
    state: "pending",
    requested_by: "builder",
    created_at: minutesAgo(12),
    resolved_at: null,
    resolved_by: null,
  },
];

// Advance the simulation: queued -> running -> completed over time.
setInterval(() => {
  const active = tasks.filter((t) => t.state === "QUEUED" || t.state === "RUNNING");
  if (active.length === 0) return;
  const t = active[Math.floor(Math.random() * active.length)];
  if (t.state === "QUEUED") {
    t.state = "RUNNING";
    t.attempts = 1;
  } else {
    t.state = "COMPLETED";
    t.result = JSON.stringify({ summary: "done" });
  }
  t.updated_at = now();
}, 7000);

function slugify(s: string): string {
  return (
    s.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40) ||
    "project"
  );
}

export async function demoGetStatus(): Promise<StatusResponse> {
  const counts: Record<string, number> = {};
  for (const t of tasks) counts[t.state] = (counts[t.state] ?? 0) + 1;
  return {
    online: true,
    demo_mode: true,
    auth_required: false,
    workers: 1,
    current_user: { name: "Mohammed Farhan", role: "Owner", is_admin: true },
    counts: {
      projects: projects.length,
      tasks: counts,
      pending_approvals: approvals.filter((a) => a.state === "pending").length,
    },
  };
}

export async function demoSendChat(message: string): Promise<ChatReply> {
  const text = message.trim();
  if (text.startsWith("/")) {
    const cmd = text.slice(1).split(" ")[0];
    const help =
      "Commands: /help — this list · /status — queue snapshot · /approvals — pending count";
    if (cmd === "help") return { reply: help };
    if (cmd === "status") {
      return { reply: await statusSummary() };
    }
    if (cmd === "approvals") {
      const n = approvals.filter((a) => a.state === "pending").length;
      return { reply: n === 0 ? "No pending approvals." : `${n} approval(s) waiting in the Approvals tab.` };
    }
    return { reply: `Unknown command /${cmd}. Try /help.` };
  }

  // Real brain if the owner connected one — otherwise the built-in engine.
  const brain = await loadBrainConfig().catch(() => null);
  if (brain) {
    try {
      return await brainChatReply(text, brain);
    } catch (e) {
      const why = e instanceof Error ? e.message : "request failed";
      const fallback = await localSmartReply(text);
      return {
        reply: `⚠️ The real brain didn't answer (${why}) — built-in mode instead.\n\n${fallback.reply}`,
        project_id: fallback.project_id,
      };
    }
  }
  return localSmartReply(text);
}

// ---------------------------------------------------------------------------
// Project actions shared by local chat and brain ACTIONs
// ---------------------------------------------------------------------------

/** Create a project with a 5-task agent plan. Used by local chat and brain. */
function createProjectLocally(title: string, description: string): ChatReply {
  const pid = nextProjectId++;
  const planTitles = [
    `Scope "${title.slice(0, 42)}"`,
    "Research the best approach",
    "Break work into milestones",
    "Draft the execution checklist",
    "Review and finalize",
  ];
  const planAgents = ["planner", "researcher", "planner", "builder", "reviewer"];
  planTitles.forEach((t, i) => {
    tasks.push(mkTask(pid, t, planAgents[i], i === 0 ? "RUNNING" : "QUEUED", t));
  });
  tasks.find((t) => t.project_id === pid && t.state === "RUNNING")!.attempts = 1;
  projects.push({
    id: pid,
    name: slugify(title),
    description,
    status: "active",
    completion_conditions: JSON.stringify(planTitles.slice(0, 3)),
    created_at: now(),
    updated_at: now(),
  });

  const reply =
    `On it. I've created the project "${slugify(title)}" with ${planTitles.length} tasks:\n\n` +
    planTitles.map((t, i) => `${i + 1}. ${t} (${planAgents[i]})`).join("\n") +
    `\n\nAgents are already working — watch it live on the Dashboard, or open the project to follow each task.`;
  return { reply, project_id: pid };
}

async function statusSummary(): Promise<string> {
  const s = await demoGetStatus();
  const parts = Object.entries(s.counts.tasks)
    .map(([k, v]) => `${v} ${k}`)
    .join(", ");
  return `Live status: ${s.counts.projects} projects · ${parts || "no tasks"} · ${s.counts.pending_approvals} approval(s) waiting.`;
}

function approvalsSummary(): string {
  const pending = approvals.filter((a) => a.state === "pending");
  if (pending.length === 0) return "No approvals waiting — you're all clear.";
  return (
    `${pending.length} approval(s) waiting in the Approvals tab:\n` +
    pending.map((a) => `• ${a.subject} (from ${a.requested_by})`).join("\n")
  );
}

function workspaceSnapshot(): {
  projects: string;
  tasksSummary: string;
  approvals: string;
} {
  const projs = [...projects]
    .reverse()
    .slice(0, 8)
    .map((p) => `- ${p.name}: ${p.description} [${p.status}]`)
    .join("\n");
  const counts: Record<string, number> = {};
  for (const t of tasks) counts[t.state] = (counts[t.state] ?? 0) + 1;
  const running = tasks
    .filter((t) => t.state === "RUNNING")
    .slice(0, 6)
    .map((t) => `- ${t.title} (${t.agent})`)
    .join("\n");
  const tasksSummary = [
    Object.entries(counts)
      .map(([k, v]) => `${v} ${k}`)
      .join(", ") || "no tasks",
    running,
  ]
    .filter(Boolean)
    .join("\n");
  const pending = approvals.filter((a) => a.state === "pending");
  const appr = pending.length
    ? pending.map((a) => `- ${a.subject} (from ${a.requested_by})`).join("\n")
    : "";
  return { projects: projs, tasksSummary, approvals: appr };
}

// ---------------------------------------------------------------------------
// Real brain path
// ---------------------------------------------------------------------------

/** Rolling conversation memory for the brain (last 10 exchanges). */
const brainHistory: BrainMessage[] = [];

function pushBrainHistory(user: string, assistant: string): void {
  brainHistory.push({ role: "user", content: user });
  brainHistory.push({ role: "assistant", content: assistant });
  while (brainHistory.length > 20) brainHistory.splice(0, 2);
}

/**
 * Real-brain path: the LLM answers with the live workspace in context and
 * may emit ACTION: lines, which we execute locally — a genuine agent loop.
 */
async function brainChatReply(text: string, cfg: BrainConfig): Promise<ChatReply> {
  const snap = workspaceSnapshot();
  const system = buildSystemPrompt({
    userName: "Farhan",
    projects: snap.projects,
    tasksSummary: snap.tasksSummary,
    approvals: snap.approvals,
  });
  const raw = await askBrain(cfg, system, brainHistory, text);
  const { text: replyText, actions } = parseBrainActions(raw);
  pushBrainHistory(text, raw);

  let projectId: number | undefined;
  const extras: string[] = [];
  for (const a of actions) {
    if (a.kind === "CREATE_PROJECT") {
      const created = createProjectLocally(a.arg || text, text);
      projectId = created.project_id;
      extras.push(created.reply);
    } else if (a.kind === "SHOW_STATUS") {
      extras.push(await statusSummary());
    } else if (a.kind === "SHOW_APPROVALS") {
      extras.push(approvalsSummary());
    }
  }
  const reply = [replyText, ...extras].filter(Boolean).join("\n\n") || "Done.";
  return { reply, project_id: projectId };
}

// ---------------------------------------------------------------------------
// Built-in conversational fallback (no brain key configured)
// ---------------------------------------------------------------------------

const QUESTION_STARTS = [
  "what", "why", "how", "who", "whom", "whose", "when", "where", "which",
  "is", "are", "was", "were", "do", "does", "did", "can", "could", "would",
  "should", "will", "shall", "may", "might", "have", "has", "had",
  "explain", "define", "describe",
];

function looksLikeQuestion(t: string): boolean {
  const s = t.trim().toLowerCase();
  if (!s) return false;
  if (s.endsWith("?")) return true;
  return QUESTION_STARTS.some(
    (w) => s === w || s.startsWith(w + " ") || s.startsWith(w + ","),
  );
}

/** Questions about ARTHUR itself — answered well even without the brain. */
function localFaqAnswer(t: string): string | null {
  const s = t.trim().toLowerCase();
  if (/^(hi|hey|hello|yo|good (morning|afternoon|evening))\b/.test(s)) {
    return "Hey Farhan 👋 — good to see you. Give me a goal and I'll spin up a project with agents on it, or ask me anything about your workspace.";
  }
  if (/who are you|what are you|your name/.test(s)) {
    return "I'm ARTHUR — Autonomous Reasoning & Task Handling Utility Runtime. I'm your personal agent system: you give me goals in chat, I break them into tasks, and my agents (planner, researcher, builder, reviewer) work through them while you watch live on the Dashboard. You're my sole owner and admin.";
  }
  if (/what can you do|how do you work|^help\b/.test(s)) {
    return "Here's what I do:\n\n• Plan — tell me any goal, I create a project with a task plan\n• Work — agents move tasks QUEUED → RUNNING → COMPLETED, live\n• Approve — risky agent actions pause for your tap in the Approvals tab\n• Report — /status for a snapshot, /approvals for what's waiting\n\nConnect the real brain in Settings → AI BRAIN and I answer anything, like a full AI assistant.";
  }
  if (/real brain|ai brain|smarter|api key/.test(s)) {
    return "The real brain connects ARTHUR to a frontier AI model (Gemini, GPT, or similar). Go to Settings → AI BRAIN, pick a provider, and paste an API key — a free one from Google AI Studio (aistudio.google.com/apikey) works. Your key stays encrypted on your device. Once it's on, I answer questions properly instead of just planning projects.";
  }
  if (/demo mode/.test(s)) {
    return "You're in demo mode: no server needed, everything runs simulated right on your device — chat, projects, tasks, approvals, all live. To use your own ARTHUR server instead, enter its HTTPS URL in Settings → ARTHUR SERVER.";
  }
  if (/approval/.test(s)) {
    return "Approvals are my safety brake: when an agent wants to do something sensitive, it pauses and asks you. Open the Approvals tab, review the request, and tap Approve or Deny. Nothing risky runs without your say-so.";
  }
  if (/server|backend|self-host|hosting/.test(s)) {
    return "The ARTHUR backend is a Python server (in the project repo) with a real task queue, worker agents, and login. Host it anywhere with a public HTTPS URL, paste the URL in Settings → ARTHUR SERVER, and this app switches from demo to your live system.";
  }
  if (/thank/.test(s)) {
    return "Anytime, Farhan. What's next?";
  }
  if (/^(bye|goodbye|see you)/.test(s)) {
    return "Later, Farhan — your agents keep working while you're away. 👋";
  }
  return null;
}

/**
 * Built-in reply: ARTHUR questions answered directly, real questions get an
 * honest pointer to the brain, and goals become projects.
 */
async function localSmartReply(text: string): Promise<ChatReply> {
  // No artificial delay — answer instantly like ChatGPT.
  const faq = localFaqAnswer(text);
  if (faq) return { reply: faq };

  if (looksLikeQuestion(text)) {
    return {
      reply:
        "Straight answer: my built-in mind is great at planning projects and running this workspace, but for deep, open-ended questions you want the real brain.\n\n" +
        "It's a one-minute setup: Settings → AI BRAIN, free key from Google AI Studio (aistudio.google.com/apikey). Then ask me anything.\n\n" +
        "Or give me a goal right now and I'll put agents on it.",
    };
  }
  return createProjectLocally(text, text);
}

export async function demoGetProjects(): Promise<Project[]> {
  return [...projects].reverse();
}

export async function demoGetTasks(projectId?: number): Promise<Task[]> {
  return tasks.filter((t) => projectId == null || t.project_id === projectId);
}

export async function demoGetAgents(): Promise<AgentStatus[]> {
  const running = tasks.some((t) => t.state === "RUNNING");
  return agents.map((a) => ({
    ...a,
    status: running && (a.name === "planner" || a.name === "builder") ? "working" : "idle",
  }));
}

export async function demoGetApprovals(): Promise<Approval[]> {
  return approvals.filter((a) => a.state === "pending");
}

export async function demoResolveApproval(
  id: number,
  approved: boolean,
): Promise<{ ok: boolean }> {
  const a = approvals.find((x) => x.id === id);
  if (a) {
    a.state = approved ? "approved" : "denied";
    a.resolved_at = now();
    a.resolved_by = "Mohammed Farhan";
  }
  return { ok: true };
}
