import { useEffect, useState } from "react";
import { StatusBar, Text, TouchableOpacity, View } from "react-native";
import { Stack, useRouter, useSegments } from "expo-router";
import { AuthProvider, useAuth } from "../lib/auth";
import {
  API_URL_STORAGE_KEY,
  getStatus,
  isDemoMode,
  setApiBaseOverride,
  type StatusResponse,
} from "../lib/api";
import { getItem } from "../lib/storage";
import { registerForPushNotifications } from "../lib/notifications";
import { theme } from "../lib/theme";

export function SignOutButton() {
  const { signOut } = useAuth();
  // Demo mode has no session to sign out of.
  if (isDemoMode()) return null;
  return (
    <TouchableOpacity
      onPress={() => void signOut()}
      style={{ marginRight: 12, padding: 6 }}
    >
      <Text style={{ color: theme.colors.primary, fontWeight: "700" }}>
        Sign out
      </Text>
    </TouchableOpacity>
  );
}

function withTimeout<T>(p: Promise<T>, ms: number): Promise<T> {
  return Promise.race([
    p,
    new Promise<never>((_, rej) =>
      setTimeout(() => rej(new Error("timeout")), ms),
    ),
  ]);
}

/** Startup gate: probe the backend. Reachable -> server auth flow.
/// Unreachable -> demo mode (the app just runs, no login needed). */
function AuthGate() {
  const { loading, token, enterDemoMode } = useAuth();
  const segments = useSegments();
  const router = useRouter();
  // undefined = probing, null = demo mode, StatusResponse = server mode
  const [server, setServer] = useState<StatusResponse | null | undefined>(
    undefined,
  );

  useEffect(() => {
    (async () => {
      try {
        const saved = await getItem(API_URL_STORAGE_KEY);
        if (saved) setApiBaseOverride(saved);
      } catch {
        // no saved override
      }
      try {
        const s = await withTimeout(getStatus(), 6000);
        setServer(s);
      } catch {
        enterDemoMode();
        setServer(null);
      }
    })();
  }, [enterDemoMode]);

  useEffect(() => {
    if (loading || server === undefined) return;
    if (server === null || isDemoMode()) {
      if (segments[0] !== "(tabs)") router.replace("/(tabs)");
      return;
    }
    if (!server.auth_required) {
      if (segments[0] !== "(tabs)") router.replace("/(tabs)");
      return;
    }
    const onLogin = segments[0] === "login";
    if (!token && !onLogin) {
      router.replace("/login");
    } else if (token && onLogin) {
      router.replace("/(tabs)");
    }
  }, [loading, token, segments, router, server]);

  return null;
}

function RootNavigator() {
  useEffect(() => {
    // Register this device for ARTHUR push notifications on mount.
    registerForPushNotifications().catch(() => undefined);
  }, []);

  return (
    <View style={{ flex: 1, backgroundColor: theme.colors.background }}>
      <StatusBar barStyle="light-content" />
      <AuthGate />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: theme.colors.background },
          headerTintColor: theme.colors.text,
          headerTitleStyle: { color: theme.colors.text, fontWeight: "700" },
          headerShadowVisible: false,
          contentStyle: { backgroundColor: theme.colors.background },
        }}
      >
        <Stack.Screen
          name="login"
          options={{ title: "Sign In", headerShown: false }}
        />
        <Stack.Screen
          name="(tabs)"
          options={{
            headerShown: false,
          }}
        />
        <Stack.Screen
          name="projects/[id]"
          options={{
            title: "Project",
            headerRight: () => <SignOutButton />,
          }}
        />
      </Stack>
    </View>
  );
}

export default function RootLayout() {
  return (
    <AuthProvider>
      <RootNavigator />
    </AuthProvider>
  );
}
