// Bottom tab bar — clean minimal tabs in the muse.ai spirit.
import { Tabs } from "expo-router";
import { Ionicons } from "@expo/vector-icons";
import { SignOutButton } from "../_layout";
import { theme } from "../../lib/theme";

const TABS = [
  { name: "index", title: "Chat", icon: "chatbubble-ellipses" },
  { name: "dashboard", title: "Dashboard", icon: "grid" },
  { name: "approvals", title: "Approvals", icon: "checkmark-circle" },
  { name: "projects", title: "Projects", icon: "folder" },
  { name: "settings", title: "Settings", icon: "settings" },
] as const;

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: {
          backgroundColor: theme.colors.background,
          shadowColor: "transparent",
          elevation: 0,
        },
        headerTintColor: theme.colors.text,
        headerTitleStyle: { color: theme.colors.text, fontWeight: "700", fontSize: 17 },
        headerRight: () => <SignOutButton />,
        tabBarStyle: {
          backgroundColor: "#1E1E22",
          borderTopColor: "#2E2E32",
          borderTopWidth: 1,
          paddingTop: 8,
          height: 68,
          elevation: 0,
        },
        tabBarActiveTintColor: "#FFFFFF",
        tabBarInactiveTintColor: "#6E6E73",
        tabBarLabelStyle: { fontSize: 11, fontWeight: "600", marginBottom: 8, marginTop: 2 },
      }}
    >
      {TABS.map((t) => (
        <Tabs.Screen
          key={t.name}
          name={t.name}
          options={{
            title: t.title === "Chat" ? "ARTHUR" : t.title,
            headerShown: t.name !== "index",
            tabBarLabel: t.title,
            tabBarIcon: ({ focused, color }) => (
              <Ionicons
                name={t.icon as keyof typeof Ionicons.glyphMap}
                size={24}
                color={color}
                style={{ opacity: focused ? 1 : 0.75 }}
              />
            ),
          }}
        />
      ))}
    </Tabs>
  );
}
