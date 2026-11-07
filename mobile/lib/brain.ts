// ARTHUR's real AI brain: bring-your-own-key connection to a frontier LLM
// over the OpenAI-compatible chat-completions API.
//
// How it works:
// - The owner pastes an API key once in Settings → AI BRAIN. The key lives
//   in the device's secure storage (SecureStore / keychain) and is only ever
//   sent to the provider the owner chose.
// - Chat messages go to the model with a system prompt describing ARTHUR,
//   the live workspace, and a tiny action grammar. The model can answer
//   directly or emit ACTION: lines, which the app executes locally
//   (create project, show status, show approvals) — a real agent loop.
// - No key configured → the app falls back to the built-in demo engine.

import { deleteItem, getItem, setItem } from "./storage";

export type BrainProvider = "gemini" | "openai" | "groq" | "custom";

export interface BrainConfig {
  provider: BrainProvider;
  baseUrl: string;
  apiKey: string;
  model: string;
}

export const BRAIN_KEYS = {
  provider: "arthur.brain.provider",
  baseUrl: "arthur.brain.base_url",
  apiKey: "arthur.brain.key",
  model: "arthur.brain.model",
} as const;

export const PROVIDER_PRESETS: Record<
  BrainProvider,
  { baseUrl: string; model: string; keyUrl: string; blurb: string }
> = {
  gemini: {
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-2.0-flash",
    keyUrl: "https://aistudio.google.com/apikey",
    blurb: "Free key from Google AI Studio — the easiest free start.",
  },
  openai: {
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    keyUrl: "https://platform.openai.com/api-keys",
    blurb: "Your own OpenAI API key.",
  },
  groq: {
    baseUrl: "https://api.groq.com/openai/v1",
    model: "llama-3.3-70b-versatile",
    keyUrl: "https://console.groq.com/keys",
    blurb: "Fast answers, generous free tier.",
  },
  custom: {
    baseUrl: "",
    model: "",
    keyUrl: "",
    blurb: "Any OpenAI-compatible endpoint.",
  },
};

export async function loadBrainConfig(): Promise<BrainConfig | null> {
  const [provider, baseUrl, apiKey, model] = await Promise.all([
    getItem(BRAIN_KEYS.provider),
    getItem(BRAIN_KEYS.baseUrl),
    getItem(BRAIN_KEYS.apiKey),
    getItem(BRAIN_KEYS.model),
  ]);
  if (!apiKey?.trim() || !baseUrl?.trim() || !model?.trim()) return null;
  return {
    provider: (provider as BrainProvider) || "custom",
    baseUrl: baseUrl.trim().replace(/\/+$/, ""),
    apiKey: apiKey.trim(),
    model: model.trim(),
  };
}

export async function saveBrainConfig(cfg: BrainConfig): Promise<void> {
  await Promise.all([
    setItem(BRAIN_KEYS.provider, cfg.provider),
    setItem(BRAIN_KEYS.baseUrl, cfg.baseUrl),
    setItem(BRAIN_KEYS.apiKey, cfg.apiKey),
    setItem(BRAIN_KEYS.model, cfg.model),
  ]);
}

export async function clearBrainConfig(): Promise<void> {
  await Promise.all(Object.values(BRAIN_KEYS).map((k) => deleteItem(k)));
}

export interface BrainAction {
  kind: "CREATE_PROJECT" | "SHOW_STATUS" | "SHOW_APPROVALS";
  arg: string;
}

export interface BrainResult {
  text: string;
  actions: BrainAction[];
}

const ACTION_RE = /^ACTION:(CREATE_PROJECT|SHOW_STATUS|SHOW_APPROVALS)(?::(.*))?$/i;

/** Split a model reply into human text + executable ACTION lines. */
export function parseBrainActions(raw: string): BrainResult {
  const actions: BrainAction[] = [];
  const textLines: string[] = [];
  for (const line of raw.split("\n")) {
    const m = line.trim().match(ACTION_RE);
    if (m) {
      actions.push({
        kind: m[1].toUpperCase() as BrainAction["kind"],
        arg: (m[2] ?? "").trim(),
      });
    } else {
      textLines.push(line);
    }
  }
  return { text: textLines.join("\n").trim(), actions };
}

export interface WorkspaceSnapshot {
  userName: string;
  projects: string;
  tasksSummary: string;
  approvals: string;
}

export function buildSystemPrompt(ctx: WorkspaceSnapshot): string {
  return [
    `You are ARTHUR — Autonomous Reasoning & Task Handling Utility Runtime, a futuristic personal AI agent system. Your sole owner and administrator is ${ctx.userName}. You are warm, sharp, and genuinely helpful. Keep answers tight unless detail is asked for. Never reveal or repeat passwords, API keys, or secrets.`,
    ``,
    `You run inside a mobile app with a live workspace:`,
    `- Projects: the user's goals. Each project gets tasks run by agents (planner, researcher, builder, reviewer).`,
    `- Tasks move QUEUED → RUNNING → COMPLETED on their own; the user watches them live.`,
    `- Approvals: some agent actions pause for the owner's tap in the Approvals tab.`,
    ``,
    `Current workspace:`,
    `PROJECTS:`,
    ctx.projects || "(no projects yet)",
    `TASKS:`,
    ctx.tasksSummary || "(no tasks)",
    `APPROVALS:`,
    ctx.approvals || "(none pending)",
    ``,
    `HOW TO ACT:`,
    `- Answer questions directly and well — you are the brain, not a menu.`,
    `- When the user gives you a GOAL or something to get done, spin up a project: emit a line exactly like`,
    `  ACTION:CREATE_PROJECT: <short title, under 8 words>`,
    `  You may write one short line before it. Do not write anything after it on the same line.`,
    `- To report live status: a line exactly like  ACTION:SHOW_STATUS`,
    `- To surface pending approvals: a line exactly like  ACTION:SHOW_APPROVALS`,
    `- Only one action per line. Never invent projects, tasks, or approvals beyond the workspace above.`,
    `- Never claim web browsing, image vision, or real-world actions outside this workspace.`,
  ].join("\n");
}

export interface BrainMessage {
  role: "user" | "assistant";
  content: string;
}

export async function askBrain(
  cfg: BrainConfig,
  system: string,
  history: BrainMessage[],
  userMessage: string,
  timeoutMs = 60000,
): Promise<string> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${cfg.baseUrl}/chat/completions`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${cfg.apiKey}`,
      },
      body: JSON.stringify({
        model: cfg.model,
        temperature: 0.7,
        max_tokens: 900,
        messages: [
          { role: "system", content: system },
          ...history.slice(-10),
          { role: "user", content: userMessage },
        ],
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      let detail = "";
      try {
        detail = (await res.text()).slice(0, 160);
      } catch {
        detail = "";
      }
      throw new Error(
        `Brain error ${res.status}${detail ? `: ${detail}` : ""}`,
      );
    }
    const data = (await res.json()) as {
      choices?: { message?: { content?: string } }[];
    };
    const text = data?.choices?.[0]?.message?.content;
    if (!text || typeof text !== "string" || !text.trim()) {
      throw new Error("The brain returned an empty answer.");
    }
    return text;
  } catch (e) {
    if (e instanceof Error && e.name === "AbortError") {
      throw new Error("The brain took too long to answer (60s timeout).");
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

/** Quick connectivity check used by the Settings test button. */
export async function testBrain(
  cfg: BrainConfig,
): Promise<{ ok: boolean; message: string }> {
  try {
    const reply = await askBrain(
      cfg,
      "You are ARTHUR. Reply with exactly: Brain online.",
      [],
      "ping",
      30000,
    );
    return /brain online/i.test(reply)
      ? {
          ok: true,
          message: "Brain online — ARTHUR now thinks with a real model.",
        }
      : { ok: true, message: "Connected — the model answered." };
  } catch (e) {
    return {
      ok: false,
      message: e instanceof Error ? e.message : "Connection failed.",
    };
  }
}
