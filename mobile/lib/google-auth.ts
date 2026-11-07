// "Continue with Google" sign-in for ARTHUR.
//
// How it works:
// - The owner creates OAuth client IDs once in Google Cloud Console
//   (numbered steps are in Settings → Google Sign-In) and pastes them
//   into the app. They live in secure storage, never in code.
// - Tapping the button opens the Google account chooser in the system
//   browser (expo-auth-session). Google returns an ID token.
// - If an ARTHUR backend is reachable, the ID token is exchanged there
//   for an ARTHUR session (POST /api/auth/google). Otherwise the Google
//   identity is used for demo mode — the app runs as that Google user.

import { useEffect, useState } from "react";
import * as WebBrowser from "expo-web-browser";
import * as Google from "expo-auth-session/providers/google";
import type { AuthSessionResult } from "expo-auth-session";
import { deleteItem, getItem, setItem } from "./storage";

WebBrowser.maybeCompleteAuthSession();

export const GOOGLE_CLIENT_KEYS = {
  android: "arthur.google.android_client_id",
  web: "arthur.google.web_client_id",
  profile: "arthur.google.profile",
} as const;

export interface GoogleClientIds {
  android: string | null;
  web: string | null;
}

export interface GoogleProfile {
  name: string;
  email: string;
  picture?: string;
}

export async function getGoogleClientIds(): Promise<GoogleClientIds> {
  const [android, web] = await Promise.all([
    getItem(GOOGLE_CLIENT_KEYS.android),
    getItem(GOOGLE_CLIENT_KEYS.web),
  ]);
  return {
    android: android?.trim() || null,
    web: web?.trim() || null,
  };
}

export async function saveGoogleClientIds(
  android: string,
  web: string,
): Promise<void> {
  await Promise.all([
    setItem(GOOGLE_CLIENT_KEYS.android, android.trim()),
    setItem(GOOGLE_CLIENT_KEYS.web, web.trim()),
  ]);
}

export async function clearGoogleClientIds(): Promise<void> {
  await Promise.all([
    deleteItem(GOOGLE_CLIENT_KEYS.android),
    deleteItem(GOOGLE_CLIENT_KEYS.web),
  ]);
}

export async function getGoogleProfile(): Promise<GoogleProfile | null> {
  try {
    const raw = await getItem(GOOGLE_CLIENT_KEYS.profile);
    return raw ? (JSON.parse(raw) as GoogleProfile) : null;
  } catch {
    return null;
  }
}

export async function saveGoogleProfile(p: GoogleProfile): Promise<void> {
  await setItem(GOOGLE_CLIENT_KEYS.profile, JSON.stringify(p));
}

export async function clearGoogleProfile(): Promise<void> {
  await deleteItem(GOOGLE_CLIENT_KEYS.profile);
}

/**
 * Hook wiring the Google auth request. Safe to call even before the
 * owner pastes client IDs — `configured` is false and the UI shows the
 * setup hint instead of starting the flow.
 */
export function useGoogleAuth() {
  const [ids, setIds] = useState<GoogleClientIds | null>(null);

  useEffect(() => {
    void getGoogleClientIds().then(setIds);
  }, []);

  const [request, response, promptAsync] = Google.useAuthRequest({
    androidClientId: ids?.android ?? undefined,
    webClientId: ids?.web ?? undefined,
  });

  return {
    request,
    response,
    promptAsync,
    configured: !!(ids && (ids.android || ids.web)),
    reloadIds: () => void getGoogleClientIds().then(setIds),
  };
}

export interface GoogleTokens {
  idToken: string;
  accessToken: string;
}

/** Pull tokens out of a successful auth response. */
export function tokensFromResponse(
  response: AuthSessionResult,
): GoogleTokens | null {
  if (response.type !== "success") return null;
  const auth = (
    response as { authentication?: { idToken?: string; accessToken?: string } }
  ).authentication;
  if (!auth?.idToken || !auth.accessToken) return null;
  return { idToken: auth.idToken, accessToken: auth.accessToken };
}

/** Resolve the Google account's public profile from an access token. */
export async function fetchGoogleProfile(
  accessToken: string,
): Promise<GoogleProfile> {
  const res = await fetch("https://www.googleapis.com/oauth2/v3/userinfo", {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) throw new Error("Could not read your Google profile.");
  const data = (await res.json()) as {
    name?: string;
    email?: string;
    picture?: string;
  };
  const name = data.name?.trim() || data.email?.trim() || "there";
  if (!data.email) throw new Error("Google did not share an email address.");
  return { name, email: data.email, picture: data.picture };
}
