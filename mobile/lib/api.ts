// Typed API client for the ARTHUR FastAPI backend.
// Endpoints mirror backend/api/server.py exactly (see CONTRACTS.md).
//
// Auth: the backend issues expiring bearer tokens via POST /api/auth/login.
// The token lives in secure storage (SecureStore on native, localStorage on web — see lib/storage.ts); this module only
// holds it in memory for the current session and attaches it as a
// Bearer header. A 401 response surfaces as AuthError so the UI can
// force a logout (session expired / revoked).

import {
  demoGetAgents,
  demoGetApprovals,
  demoGetProjects,
  demoGetStatus,
  demoGetTasks,
  demoResolveApproval,
  demoSendChat,
} from "./demo-engine";

const DEFAULT_API_BASE: string =
  process.env.EXPO_PUBLIC_ARTHUR_API_URL ?? "http://localhost:8000";

let apiBaseOverride: string | null = null;
let demoMode = false;

/** Full base URL in use: runtime override (Settings) wins over build-time. */
export const API_URL_STORAGE_KEY = "arthur.api_base_override";

/** Full base URL in use: runtime override (Settings) wins over build-time. */
export function apiBase(): string {
  return apiBaseOverride ?? DEFAULT_API_BASE;
}

/** Persisted server URL override, e.g. https://arthur.example.com */
export function setApiBaseOverride(url: string | null): void {
  apiBaseOverride = url && url.trim() ? url.trim().replace(/\/+$/, "") : null;
}

export function getApiBaseOverride(): string | null {
  return apiBaseOverride;
}

/** Demo mode: all API calls are served by the in-app simulated engine. */
export function setDemoMode(on: boolean): void {
  demoMode = on;
}

export function isDemoMode(): boolean {
  return demoMode;
}

export class AuthError extends Error {
  constructor(message = "Session expired — please sign in again.") {
    super(message);
    this.name = "AuthError";
  }
}

let authToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

/** Called by the AuthProvider after login / logout / app start. */
export function setAuthToken(token: string | null): void {
  authToken = token;
}

/** Called by the AuthProvider so a 401 anywhere forces a logout. */
export function setOnUnauthorized(cb: (() => void) | null): void {
  onUnauthorized = cb;
}

export interface CurrentUser {
  name: string;
  role: string;
  is_admin: number | boolean;
}

export interface LoginResponse {
  token: string;
  expires_at: string;
  user: CurrentUser;
}

export interface StatusResponse {
  online: boolean;
  demo_mode: boolean;
  auth_required: boolean;
  workers: number;
  current_user: CurrentUser | null;
  counts: {
    projects: number;
    tasks: Record<string, number>;
    pending_approvals: number;
  };
}

export interface Project {
  id: number;
  name: string;
  description: string;
  status: string;
  completion_conditions: string; // JSON list
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: number;
  project_id: number;
  title: string;
  agent: string;
  deps: string; // JSON list of ids
  state: string;
  attempts: number;
  max_attempts: number;
  checkpoint: string; // JSON
  result: string | null; // JSON
  error: string | null;
  success_criteria: string;
  steps: string; // JSON list
  next_retry_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface AgentStatus {
  id: number;
  name: string;
  kind: string;
  permission_level: number;
  status: string;
}

export interface Approval {
  id: number;
  kind: string;
  subject: string;
  detail: string; // JSON
  state: string;
  requested_by: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
}

export interface LogEntry {
  id: number;
  ts: string;
  agent: string;
  tool: string;
  args: string; // JSON
  ok: number;
  error: string | null;
}

export interface ChatMessage {
  role: "user" | "arthur";
  content: string;
}

export interface ChatReply {
  reply: string;
  project_id?: number;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (authToken) {
    headers["Authorization"] = `Bearer ${authToken}`;
  }
  const res = await fetch(`${apiBase()}${path}`, {
    ...init,
    headers: { ...headers, ...(init?.headers as Record<string, string>) },
  });
  if (res.status === 401) {
    onUnauthorized?.();
    throw new AuthError();
  }
  if (!res.ok) {
    let detail = "";
    try {
      detail = await res.text();
    } catch {
      detail = "";
    }
    throw new Error(
      `ARTHUR API ${res.status} ${res.statusText}${detail ? `: ${detail}` : ""}`,
    );
  }
  return (await res.json()) as T;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

export async function login(
  name: string,
  password: string,
): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ name, password }),
  });
}

/** Exchange a Google ID token for an ARTHUR session (server mode). */
export async function googleLogin(idToken: string): Promise<LoginResponse> {
  return request<LoginResponse>("/api/auth/google", {
    method: "POST",
    body: JSON.stringify({ id_token: idToken }),
  });
}

export async function logout(): Promise<void> {
  try {
    await request<{ ok: boolean }>("/api/auth/logout", { method: "POST" });
  } catch {
    // Best effort: the local session is cleared regardless.
  }
}

export async function getMe(): Promise<CurrentUser> {
  return request<CurrentUser>("/api/auth/me");
}

// ---------------------------------------------------------------------------
// App endpoints
// ---------------------------------------------------------------------------

export async function getStatus(): Promise<StatusResponse> {
  if (demoMode) return demoGetStatus();
  return request<StatusResponse>("/api/status");
}

export async function sendChat(message: string): Promise<ChatReply> {
  if (demoMode) return demoSendChat(message);
  return request<ChatReply>("/api/chat", {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export async function getProjects(): Promise<Project[]> {
  if (demoMode) return demoGetProjects();
  return request<Project[]>("/api/projects");
}

export async function getTasks(projectId?: number): Promise<Task[]> {
  if (demoMode) return demoGetTasks(projectId);
  const q = projectId != null ? `?project_id=${projectId}` : "";
  return request<Task[]>(`/api/tasks${q}`);
}

export async function getAgents(): Promise<AgentStatus[]> {
  if (demoMode) return demoGetAgents();
  return request<AgentStatus[]>("/api/agents");
}

export async function getApprovals(): Promise<Approval[]> {
  if (demoMode) return demoGetApprovals();
  return request<Approval[]>("/api/approvals");
}

export async function resolveApproval(
  id: number,
  approved: boolean,
): Promise<{ ok: boolean }> {
  if (demoMode) return demoResolveApproval(id, approved);
  return request<{ ok: boolean }>(`/api/approvals/${id}/resolve`, {
    method: "POST",
    body: JSON.stringify({ approved }),
  });
}

export async function getLogs(limit = 100): Promise<LogEntry[]> {
  return request<LogEntry[]>(`/api/logs?limit=${limit}`);
}

export async function registerPushToken(
  token: string,
  platform: string,
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>("/api/push/register", {
    method: "POST",
    body: JSON.stringify({ token, platform }),
  });
}
