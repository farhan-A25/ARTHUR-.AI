import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { registerPushToken } from "./api";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowBanner: true,
    shouldShowList: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
  }),
});

interface ExpoConfigExtra {
  extra?: {
    eas?: {
      projectId?: string;
    };
  };
}

/**
 * Request notification permissions, fetch the Expo push token, and register
 * it with the ARTHUR backend via POST /api/push/register.
 * Returns the token, or null on failure / denial.
 */
export async function registerForPushNotifications(): Promise<string | null> {
  try {
    if (Platform.OS === "android") {
      await Notifications.setNotificationChannelAsync("default", {
        name: "default",
        importance: Notifications.AndroidImportance.MAX,
        vibrationPattern: [0, 250, 250, 250],
        lightColor: "#38E1FF",
      });
    }

    const current = await Notifications.getPermissionsAsync();
    let granted = current.granted;
    if (!granted) {
      const requested = await Notifications.requestPermissionsAsync();
      granted = requested.granted;
    }
    if (!granted) {
      return null;
    }

    const expoConfig = Constants.expoConfig as ExpoConfigExtra | undefined;
    const projectId = expoConfig?.extra?.eas?.projectId;

    const tokenResponse = projectId
      ? await Notifications.getExpoPushTokenAsync({ projectId })
      : await Notifications.getExpoPushTokenAsync();

    const token = tokenResponse.data;
    await registerPushToken(token, Platform.OS);
    return token;
  } catch {
    return null;
  }
}
