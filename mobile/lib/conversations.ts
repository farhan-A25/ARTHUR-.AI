// Persistent chat conversations (ChatGPT-style sidebar history).
// Stored in AsyncStorage as JSON; newest first.

import AsyncStorage from "@react-native-async-storage/async-storage";

export interface StoredMessage {
  role: "user" | "arthur";
  content: string;
  ts: number;
  projectId?: number;
}

export interface Conversation {
  id: string;
  title: string;
  createdAt: number;
  updatedAt: number;
  messages: StoredMessage[];
}

const STORAGE_KEY = "arthur.conversations.v1";

export function createConversation(): Conversation {
  const now = Date.now();
  return {
    id: `${now.toString(36)}${Math.random().toString(36).slice(2, 8)}`,
    title: "New chat",
    createdAt: now,
    updatedAt: now,
    messages: [],
  };
}

/** Short title derived from the first user message. */
export function titleFromText(text: string): string {
  const t = text.trim().replace(/\s+/g, " ");
  return t.length > 42 ? `${t.slice(0, 42)}…` : t || "New chat";
}

export async function loadConversations(): Promise<Conversation[]> {
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Conversation[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((c) => c && typeof c.id === "string" && Array.isArray(c.messages))
      .sort((a, b) => b.updatedAt - a.updatedAt);
  } catch {
    return [];
  }
}

export async function saveConversations(list: Conversation[]): Promise<void> {
  try {
    // Cap stored history so the payload stays small.
    const trimmed = list.slice(0, 100).map((c) => ({
      ...c,
      messages: c.messages.slice(-200),
    }));
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // storage full — chat still works in memory for this session
  }
}
