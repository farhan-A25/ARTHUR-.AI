// Settings: server connection, demo mode, sign out, about.

import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import {
  API_URL_STORAGE_KEY,
  apiBase,
  getApiBaseOverride,
  isDemoMode,
  setApiBaseOverride,
} from "../../lib/api";
import {
  PROVIDER_PRESETS,
  clearBrainConfig,
  loadBrainConfig,
  saveBrainConfig,
  testBrain,
  type BrainProvider,
} from "../../lib/brain";
import { useAuth } from "../../lib/auth";
import {
  clearGoogleClientIds,
  getGoogleClientIds,
  getGoogleProfile,
  saveGoogleClientIds,
  type GoogleProfile,
} from "../../lib/google-auth";
import { deleteItem, setItem } from "../../lib/storage";
import { theme } from "../../lib/theme";

const PROVIDER_LABELS: { id: BrainProvider; label: string }[] = [
  { id: "gemini", label: "Gemini" },
  { id: "openai", label: "OpenAI" },
  { id: "groq", label: "Groq" },
  { id: "custom", label: "Custom" },
];

export default function SettingsScreen() {
  const { user, signOut } = useAuth();
  const [url, setUrl] = useState("");
  const [saved, setSaved] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const demo = isDemoMode();

  // AI brain state
  const [provider, setProvider] = useState<BrainProvider>("gemini");
  const [brainUrl, setBrainUrl] = useState(PROVIDER_PRESETS.gemini.baseUrl);
  const [brainModel, setBrainModel] = useState(PROVIDER_PRESETS.gemini.model);
  const [brainKey, setBrainKey] = useState("");
  const [brainOn, setBrainOn] = useState(false);
  const [brainBusy, setBrainBusy] = useState(false);
  const [brainMsg, setBrainMsg] = useState<string | null>(null);

  // Google sign-in state
  const [gAndroid, setGAndroid] = useState("");
  const [gWeb, setGWeb] = useState("");
  const [gOn, setGOn] = useState(false);
  const [gBusy, setGBusy] = useState(false);
  const [gMsg, setGMsg] = useState<string | null>(null);
  const [gProfile, setGProfile] = useState<GoogleProfile | null>(null);

  useEffect(() => {
    setSaved(getApiBaseOverride());
    setUrl(getApiBaseOverride() ?? "");
    void loadBrainConfig().then((cfg) => {
      if (cfg) {
        setProvider(cfg.provider);
        setBrainUrl(cfg.baseUrl);
        setBrainModel(cfg.model);
        setBrainKey(cfg.apiKey);
        setBrainOn(true);
      }
    });
    void getGoogleClientIds().then((ids) => {
      if (ids.android || ids.web) {
        setGAndroid(ids.android ?? "");
        setGWeb(ids.web ?? "");
        setGOn(true);
      }
    });
    void getGoogleProfile().then(setGProfile);
  }, []);

  function pickProvider(p: BrainProvider) {
    setProvider(p);
    const preset = PROVIDER_PRESETS[p];
    if (p !== "custom") {
      setBrainUrl(preset.baseUrl);
      setBrainModel(preset.model);
    }
    setBrainMsg(null);
  }

  async function saveBrain() {
    const key = brainKey.trim();
    const base = brainUrl.trim().replace(/\/+$/, "");
    const model = brainModel.trim();
    if (!key || !base || !model) {
      setBrainMsg("Fill in the API key, endpoint URL, and model name.");
      return;
    }
    setBrainBusy(true);
    setBrainMsg(null);
    try {
      const cfg = { provider, baseUrl: base, apiKey: key, model };
      const test = await testBrain(cfg);
      if (!test.ok) {
        setBrainMsg(`Not connected: ${test.message}`);
        return;
      }
      await saveBrainConfig(cfg);
      setBrainOn(true);
      setBrainMsg(test.message);
    } finally {
      setBrainBusy(false);
    }
  }

  async function removeBrain() {
    await clearBrainConfig();
    setBrainKey("");
    setBrainOn(false);
    setBrainMsg("Brain removed — back to built-in mode.");
  }

  async function saveGoogle() {
    const android = gAndroid.trim();
    const web = gWeb.trim();
    if (!android && !web) {
      setGMsg("Paste at least one Client ID from Google Cloud Console.");
      return;
    }
    setGBusy(true);
    setGMsg(null);
    try {
      await saveGoogleClientIds(android, web);
      setGOn(true);
      setGMsg(
        "Saved. Restart the app — the login screen now offers “Continue with Google”.",
      );
    } finally {
      setGBusy(false);
    }
  }

  async function removeGoogle() {
    await clearGoogleClientIds();
    setGAndroid("");
    setGWeb("");
    setGOn(false);
    setGMsg("Google sign-in removed.");
  }

  useEffect(() => {
    setSaved(getApiBaseOverride());
    setUrl(getApiBaseOverride() ?? "");
  }, []);

  async function saveUrl() {
    const clean = url.trim().replace(/\/+$/, "");
    if (!clean) {
      setNotice("Enter your server URL first.");
      return;
    }
    setBusy(true);
    try {
      await setItem(API_URL_STORAGE_KEY, clean);
      setApiBaseOverride(clean);
      setSaved(clean);
      setNotice("Saved. Restart the app to connect to your server.");
    } finally {
      setBusy(false);
    }
  }

  async function useDemo() {
    await deleteItem(API_URL_STORAGE_KEY);
    setApiBaseOverride(null);
    setSaved(null);
    setUrl("");
    setNotice("Server forgotten. Restart the app to enter demo mode.");
  }

  return (
    <ScrollView style={styles.container} contentContainerStyle={styles.content}>
      <Text style={styles.sectionTitle}>CONNECTION</Text>
      <View style={styles.card}>
        <View style={styles.statusRow}>
          <View
            style={[
              styles.dot,
              { backgroundColor: demo ? theme.colors.warning : theme.colors.success },
            ]}
          />
          <Text style={styles.statusText}>
            {demo ? "Demo mode — simulated ARTHUR" : "Connected to server"}
          </Text>
        </View>
        {!demo && <Text style={styles.url}>{apiBase()}</Text>}
        {user && (
          <Text style={styles.meta}>
            Signed in as {user.name} ({user.role})
          </Text>
        )}
      </View>

      <Text style={styles.sectionTitle}>AI BRAIN</Text>
      <View style={styles.card}>
        <View style={styles.statusRow}>
          <View
            style={[
              styles.dot,
              { backgroundColor: brainOn ? theme.colors.success : theme.colors.warning },
            ]}
          />
          <Text style={styles.statusText}>
            {brainOn ? "Real brain online" : "Built-in brain (demo)"}
          </Text>
        </View>
        <Text style={styles.help}>
          Connect a real AI model and ARTHUR answers anything, like a full AI
          assistant. Your key stays encrypted on this device.{"\n"}
          {PROVIDER_PRESETS[provider].blurb}
          {provider !== "custom" && `\nGet a key: ${PROVIDER_PRESETS[provider].keyUrl}`}
        </Text>
        <View style={styles.chipRow}>
          {PROVIDER_LABELS.map((p) => (
            <TouchableOpacity
              key={p.id}
              style={[styles.chip, provider === p.id && styles.chipActive]}
              onPress={() => pickProvider(p.id)}
            >
              <Text style={[styles.chipText, provider === p.id && styles.chipTextActive]}>
                {p.label}
              </Text>
            </TouchableOpacity>
          ))}
        </View>
        <TextInput
          style={styles.input}
          value={brainKey}
          onChangeText={setBrainKey}
          placeholder="API key"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
        />
        <TextInput
          style={styles.input}
          value={brainUrl}
          onChangeText={setBrainUrl}
          placeholder="Endpoint URL (OpenAI-compatible)"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <TextInput
          style={styles.input}
          value={brainModel}
          onChangeText={setBrainModel}
          placeholder="Model name"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.button, styles.primary]}
            onPress={() => void saveBrain()}
            disabled={brainBusy}
          >
            {brainBusy ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>SAVE & TEST BRAIN</Text>
            )}
          </TouchableOpacity>
        </View>
        {brainOn && (
          <TouchableOpacity style={styles.linkBtn} onPress={() => void removeBrain()}>
            <Text style={styles.linkText}>Remove brain & use built-in mode</Text>
          </TouchableOpacity>
        )}
        {brainMsg && <Text style={styles.notice}>{brainMsg}</Text>}
      </View>

      <Text style={styles.sectionTitle}>GOOGLE SIGN-IN</Text>
      <View style={styles.card}>
        <View style={styles.statusRow}>
          <View
            style={[
              styles.dot,
              { backgroundColor: gOn ? theme.colors.success : theme.colors.warning },
            ]}
          />
          <Text style={styles.statusText}>
            {gOn ? "Google login ready" : "Not set up"}
          </Text>
        </View>
        {gProfile && (
          <Text style={styles.meta}>
            Google account: {gProfile.name} ({gProfile.email})
          </Text>
        )}
        <Text style={styles.help}>
          Add “Continue with Google” to the login screen. Create the IDs once
          in Google Cloud Console (console.cloud.google.com → Credentials →
          Create Credentials → OAuth client ID):{"\n"}• Android type — package
          com.arthur.ai, with your app's SHA-1 fingerprint{"\n"}• Web
          application type — used as a fallback. Then paste both IDs here.
        </Text>
        <TextInput
          style={styles.input}
          value={gAndroid}
          onChangeText={setGAndroid}
          placeholder="Android Client ID (…apps.googleusercontent.com)"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <TextInput
          style={styles.input}
          value={gWeb}
          onChangeText={setGWeb}
          placeholder="Web Client ID (…apps.googleusercontent.com)"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
        />
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.button, styles.primary]}
            onPress={() => void saveGoogle()}
            disabled={gBusy}
          >
            {gBusy ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>SAVE GOOGLE LOGIN</Text>
            )}
          </TouchableOpacity>
        </View>
        {gOn && (
          <TouchableOpacity style={styles.linkBtn} onPress={() => void removeGoogle()}>
            <Text style={styles.linkText}>Remove Google sign-in</Text>
          </TouchableOpacity>
        )}
        {gMsg && <Text style={styles.notice}>{gMsg}</Text>}
      </View>

      <Text style={styles.sectionTitle}>ARTHUR SERVER</Text>
      <View style={styles.card}>
        <Text style={styles.help}>
          Host the ARTHUR backend somewhere with a public HTTPS URL, enter it
          here, and the app will use your live server instead of the demo.
        </Text>
        <TextInput
          style={styles.input}
          value={url}
          onChangeText={setUrl}
          placeholder="https://arthur.example.com"
          placeholderTextColor={theme.colors.textFaint}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
        />
        <View style={styles.row}>
          <TouchableOpacity
            style={[styles.button, styles.primary]}
            onPress={() => void saveUrl()}
            disabled={busy}
          >
            {busy ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.buttonText}>SAVE & USE SERVER</Text>
            )}
          </TouchableOpacity>
        </View>
        {saved && (
          <TouchableOpacity style={styles.linkBtn} onPress={() => void useDemo()}>
            <Text style={styles.linkText}>Forget server & use demo mode</Text>
          </TouchableOpacity>
        )}
        {notice && <Text style={styles.notice}>{notice}</Text>}
      </View>

      {!demo && (
        <>
          <Text style={styles.sectionTitle}>ACCOUNT</Text>
          <View style={styles.card}>
            <TouchableOpacity
              style={[styles.button, styles.dangerOutline]}
              onPress={() => void signOut()}
            >
              <Text style={[styles.buttonText, styles.dangerText]}>SIGN OUT</Text>
            </TouchableOpacity>
          </View>
        </>
      )}

      <Text style={styles.sectionTitle}>ABOUT</Text>
      <View style={styles.card}>
        <Text style={styles.meta}>ARTHUR 1.2.3 — Autonomous Reasoning & Task Handling Utility Runtime</Text>
        <Text style={styles.meta}>Sole owner & administrator: Mohammed Farhan</Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  content: { padding: theme.spacing.lg, gap: theme.spacing.md },
  sectionTitle: {
    color: theme.colors.textDim,
    fontSize: 13,
    fontWeight: "700",
    marginTop: theme.spacing.sm,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.lg,
    gap: theme.spacing.sm,
  },
  statusRow: { flexDirection: "row", alignItems: "center", gap: theme.spacing.sm },
  dot: { width: 10, height: 10, borderRadius: 5 },
  statusText: { color: theme.colors.text, fontWeight: "700" },
  url: { color: theme.colors.textDim, fontSize: 13 },
  meta: { color: theme.colors.textDim, fontSize: 13 },
  help: { color: theme.colors.textDim, fontSize: 13, lineHeight: 20 },
  input: {
    backgroundColor: theme.colors.surfaceAlt,
    borderWidth: 0,
    borderRadius: theme.radius.md,
    color: theme.colors.text,
    paddingHorizontal: theme.spacing.lg,
    paddingVertical: theme.spacing.md,
    fontSize: 14,
  },
  row: { flexDirection: "row", gap: theme.spacing.sm },
  button: {
    flex: 1,
    borderRadius: theme.radius.xl,
    paddingVertical: theme.spacing.md,
    alignItems: "center",
  },
  primary: { backgroundColor: theme.colors.primary },
  dangerOutline: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  buttonText: { color: "#FFFFFF", fontWeight: "700", fontSize: 14 },
  dangerText: { color: theme.colors.danger },
  linkBtn: { alignItems: "center", padding: theme.spacing.sm },
  linkText: { color: theme.colors.primary, fontSize: 13 },
  notice: { color: theme.colors.warning, fontSize: 13 },
  chipRow: { flexDirection: "row", flexWrap: "wrap", gap: theme.spacing.sm },
  chip: {
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.xl,
    paddingVertical: theme.spacing.sm,
    paddingHorizontal: theme.spacing.md,
    backgroundColor: theme.colors.surface,
  },
  chipActive: {
    borderColor: theme.colors.primary,
    backgroundColor: theme.colors.primaryDim,
  },
  chipText: { color: theme.colors.textDim, fontWeight: "600", fontSize: 13 },
  chipTextActive: { color: theme.colors.primaryDark, fontWeight: "700" },
});
