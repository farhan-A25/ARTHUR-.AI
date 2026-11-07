// ARTHUR auth state: secure token storage + session lifecycle.
//
// The session token is kept in secure storage — hardware-backed keychain /
// keystore on real devices, localStorage on web (see lib/storage.ts) — never in plain state. The
// backend session expires (ARTHUR_SESSION_HOURS, default 24h); on expiry or
// any 401 the provider logs out and the UI returns to the login screen.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { deleteItem, getItem, setItem } from "./storage";
import {
  getMe,
  getStatus,
  googleLogin,
  isDemoMode,
  login as apiLogin,
  logout as apiLogout,
  setAuthToken,
  setDemoMode,
  setOnUnauthorized,
  type CurrentUser,
} from "./api";
import {
  clearGoogleProfile,
  saveGoogleProfile,
  type GoogleProfile,
} from "./google-auth";

const TOKEN_KEY = "arthur.session_token";
const EXPIRES_KEY = "arthur.session_expires_at";

interface AuthState {
  loading: boolean;
  token: string | null;
  user: CurrentUser | null;
  signIn: (name: string, password: string) => Promise<void>;
  signInWithGoogle: (profile: GoogleProfile, idToken: string) => Promise<void>;
  signOut: () => Promise<void>;
  enterDemoMode: () => void;
}

const AuthContext = createContext<AuthState>({
  loading: true,
  token: null,
  user: null,
  signIn: async () => undefined,
  signInWithGoogle: async () => undefined,
  signOut: async () => undefined,
  enterDemoMode: () => undefined,
});

export function useAuth(): AuthState {
  return useContext(AuthContext);
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<CurrentUser | null>(null);

  const clearLocalSession = useCallback(async () => {
    setToken(null);
    setUser(null);
    setAuthToken(null);
    await deleteItem(TOKEN_KEY);
    await deleteItem(EXPIRES_KEY);
  }, []);

  const signOut = useCallback(async () => {
    await apiLogout(); // best effort server-side revoke
    await clearGoogleProfile();
    await clearLocalSession();
  }, [clearLocalSession]);

  /**
   * Google sign-in. If an ARTHUR backend is reachable, the Google ID token
   * is exchanged there for a real session. Otherwise (demo mode) the app
   * runs as the Google identity — no backend needed.
   */
  const signInWithGoogle = useCallback(
    async (profile: GoogleProfile, idToken: string) => {
      await saveGoogleProfile(profile);
      let serverMode = false;
      try {
        const s = await getStatus();
        serverMode = !isDemoMode() && !!s && s.auth_required;
      } catch {
        serverMode = false; // backend unreachable → demo mode
      }
      if (serverMode) {
        // Real backend: exchange the Google token for an ARTHUR session.
        const res = await googleLogin(idToken);
        setAuthToken(res.token);
        setToken(res.token);
        setUser(res.user);
        await setItem(TOKEN_KEY, res.token);
        await setItem(EXPIRES_KEY, res.expires_at);
        return;
      }
      setDemoMode(true);
      setAuthToken(null);
      setToken("google-demo");
      setUser({ name: profile.name, role: "Owner", is_admin: true });
      setLoading(false);
    },
    [],
  );

  // Demo mode: no backend reachable — run the in-app simulated engine.
  const enterDemoMode = useCallback(() => {
    setDemoMode(true);
    setAuthToken(null);
    setToken("demo");
    setUser({ name: "Mohammed Farhan", role: "Owner", is_admin: true });
    setLoading(false);
  }, []);

  // A 401 from any API call means the session died server-side.
  useEffect(() => {
    setOnUnauthorized(() => {
      void clearLocalSession();
    });
    return () => setOnUnauthorized(null);
  }, [clearLocalSession]);

  // Restore session on app start.
  useEffect(() => {
    (async () => {
      try {
        const savedToken = await getItem(TOKEN_KEY);
        const savedExpiry = await getItem(EXPIRES_KEY);
        if (savedToken && savedExpiry && new Date(savedExpiry) > new Date()) {
          setAuthToken(savedToken);
          try {
            const me = await getMe();
            setToken(savedToken);
            setUser(me);
          } catch {
            // Token invalid server-side (revoked / DB reset).
            await clearLocalSession();
          }
        } else if (savedToken) {
          // Past expiry — drop it.
          await clearLocalSession();
        } else {
          // No saved session: if the backend doesn't require auth (demo
          // mode), pick up the owner identity so the UI can greet by name.
          try {
            const s = await getStatus();
            if (!s.auth_required && s.current_user) {
              setUser(s.current_user);
            }
          } catch {
            // Backend unreachable — screens show their own errors.
          }
        }
      } finally {
        setLoading(false);
      }
    })();
  }, [clearLocalSession]);

  const signIn = useCallback(
    async (name: string, password: string) => {
      const res = await apiLogin(name.trim(), password);
      setAuthToken(res.token);
      setToken(res.token);
      setUser(res.user);
      await setItem(TOKEN_KEY, res.token);
      await setItem(EXPIRES_KEY, res.expires_at);
    },
    [],
  );

  const value = useMemo<AuthState>(
    () => ({
      loading,
      token,
      user,
      signIn,
      signInWithGoogle,
      signOut,
      enterDemoMode,
    }),
    [loading, token, user, signIn, signInWithGoogle, signOut, enterDemoMode],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
