// Token storage that works everywhere: hardware-backed SecureStore on
// iOS/Android, localStorage on web. Same API surface as expo-secure-store
// for the three operations auth needs.

import { Platform } from "react-native";
import * as SecureStore from "expo-secure-store";

export async function getItem(key: string): Promise<string | null> {
  if (Platform.OS === "web") {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

export async function setItem(key: string, value: string): Promise<void> {
  if (Platform.OS === "web") {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // storage full / private mode — session just won't persist
    }
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

export async function deleteItem(key: string): Promise<void> {
  if (Platform.OS === "web") {
    try {
      window.localStorage.removeItem(key);
    } catch {
      // ignore
    }
    return;
  }
  await SecureStore.deleteItemAsync(key).catch(() => undefined);
}
