// ARTHUR sign-in — ChatGPT dark style: near-black canvas, teddy,
// "Welcome back", minimal fields, one white Continue button.

import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { useAuth } from "../lib/auth";
import {
  fetchGoogleProfile,
  tokensFromResponse,
  useGoogleAuth,
} from "../lib/google-auth";

const BG = "#1A1A1E";
const FIELD = "#26262A";
const TEXT = "#FFFFFF";
const TEXT_DIM = "#A8A8AD";
const TEXT_FAINT = "#6E6E73";
const DANGER = "#E06C5B";

export default function LoginScreen() {
  const { signIn, signInWithGoogle } = useAuth();
  const { request, response, promptAsync, configured } = useGoogleAuth();
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [googleBusy, setGoogleBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Handle the Google auth response.
  useEffect(() => {
    if (!response) return;
    (async () => {
      const tokens = tokensFromResponse(response);
      if (!tokens) {
        if (response.type === "error") setError("Google sign-in failed.");
        setGoogleBusy(false);
        return;
      }
      try {
        const profile = await fetchGoogleProfile(tokens.accessToken);
        await signInWithGoogle(profile, tokens.idToken);
        // AuthGate routes into the app.
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Google sign-in failed.",
        );
      } finally {
        setGoogleBusy(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [response]);

  function handleGoogle() {
    if (googleBusy) return;
    if (!configured) {
      Alert.alert(
        "Google sign-in not set up yet",
        "Add your Google Client IDs first:\n\nSettings → Google Sign-In → paste the IDs from Google Cloud Console.",
        [{ text: "OK" }],
      );
      return;
    }
    setGoogleBusy(true);
    setError(null);
    void promptAsync().catch(() => setGoogleBusy(false));
  }

  async function handleSignIn() {
    if (busy) return;
    if (!name.trim() || !password) {
      setError("Enter your name and password to continue.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await signIn(name, password);
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Sign-in failed.";
      setError(
        msg.includes("401") || msg.toLowerCase().includes("invalid")
          ? "Wrong name or password."
          : msg,
      );
    } finally {
      setBusy(false);
    }
  }

  const ready = name.trim().length > 0 && password.length > 0 && !busy;

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={styles.inner}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        <View style={styles.center}>
          <Image
            source={require("../assets/arthur-avatar.png")}
            style={styles.logo}
            resizeMode="cover"
          />
          <Text style={styles.title}>Welcome back</Text>
          <Text style={styles.subtitle}>Sign in to ARTHUR</Text>

          <View style={styles.form}>
            <TouchableOpacity
              style={[styles.button, googleBusy && styles.buttonIdle]}
              onPress={handleGoogle}
              disabled={googleBusy || !request}
            >
              {googleBusy ? (
                <ActivityIndicator color="#1A1A1E" />
              ) : (
                <View style={styles.googleRow}>
                  <Text style={styles.googleG}>G</Text>
                  <Text style={styles.buttonText}>Continue with Google</Text>
                </View>
              )}
            </TouchableOpacity>

            <View style={styles.divider}>
              <View style={styles.dividerLine} />
              <Text style={styles.dividerText}>or</Text>
              <View style={styles.dividerLine} />
            </View>

            <TextInput
              style={styles.input}
              value={name}
              onChangeText={setName}
              placeholder="Name"
              placeholderTextColor={TEXT_FAINT}
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="next"
              editable={!busy}
            />
            <TextInput
              style={styles.input}
              value={password}
              onChangeText={setPassword}
              placeholder="Password"
              placeholderTextColor={TEXT_FAINT}
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
              returnKeyType="go"
              onSubmitEditing={() => void handleSignIn()}
              editable={!busy}
            />

            {error ? <Text style={styles.error}>{error}</Text> : null}

            <TouchableOpacity
              style={[styles.button, !ready && styles.buttonIdle]}
              onPress={() => void handleSignIn()}
              disabled={!ready}
            >
              {busy ? (
                <ActivityIndicator color="#1A1A1E" />
              ) : (
                <Text style={styles.buttonText}>Continue</Text>
              )}
            </TouchableOpacity>

            <Text style={styles.hint}>Only the owner account can sign in.</Text>
          </View>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  inner: { flex: 1 },
  center: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
    paddingHorizontal: 32,
  },
  logo: { width: 96, height: 96, borderRadius: 48, marginBottom: 28 },
  title: { color: TEXT, fontSize: 28, fontWeight: "700", marginBottom: 8 },
  subtitle: { color: TEXT_DIM, fontSize: 15, marginBottom: 32 },
  form: { width: "100%", maxWidth: 340, gap: 12 },
  input: {
    backgroundColor: FIELD,
    borderRadius: 14,
    color: TEXT,
    paddingHorizontal: 16,
    paddingVertical: 15,
    fontSize: 16,
  },
  error: { color: DANGER, fontSize: 13, textAlign: "center" },
  button: {
    backgroundColor: "#FFFFFF",
    borderRadius: 24,
    paddingVertical: 15,
    alignItems: "center",
    marginTop: 8,
  },
  buttonIdle: { opacity: 0.35 },
  buttonText: { color: "#1A1A1E", fontSize: 16, fontWeight: "600" },
  googleRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  googleG: {
    color: "#4285F4",
    fontSize: 20,
    fontWeight: "800",
  },
  divider: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginVertical: 4,
  },
  dividerLine: { flex: 1, height: 1, backgroundColor: "#2E2E32" },
  dividerText: { color: TEXT_FAINT, fontSize: 13 },
  hint: { color: TEXT_FAINT, fontSize: 12, textAlign: "center", marginTop: 12 },
});
