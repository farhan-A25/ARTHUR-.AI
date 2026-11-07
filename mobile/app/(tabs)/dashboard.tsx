import { useCallback, useEffect, useState } from "react";
import {
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import {
  getAgents,
  getProjects,
  getStatus,
  getTasks,
  type AgentStatus,
  type Project,
  type StatusResponse,
  type Task,
} from "../../lib/api";
import { theme } from "../../lib/theme";

const TERMINAL = new Set(["COMPLETED", "FAILED"]);

function isAdmin(value: number | boolean): boolean {
  return value === 1 || value === true;
}

function ProgressBar({ pct }: { pct: number }) {
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${pct}%` }]} />
    </View>
  );
}

export default function DashboardScreen() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [agents, setAgents] = useState<AgentStatus[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, p, a, t] = await Promise.all([
        getStatus(),
        getProjects(),
        getAgents(),
        getTasks(),
      ]);
      setStatus(s);
      setProjects(p);
      setAgents(a);
      setTasks(t);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Backend unreachable");
    }
  }, []);

  useEffect(() => {
    void load();
    const id = setInterval(() => {
      void load();
    }, 3000);
    return () => clearInterval(id);
  }, [load]);

  const done = tasks.filter((t) => TERMINAL.has(t.state)).length;
  const pct = tasks.length > 0 ? Math.round((done / tasks.length) * 100) : 0;
  const user = status?.current_user;
  const online = status?.online ?? false;
  const counts = status?.counts;

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={refreshing}
          tintColor={theme.colors.primary}
          onRefresh={async () => {
            setRefreshing(true);
            await load();
            setRefreshing(false);
          }}
        />
      }
    >
      {/* Status pill + user */}
      <View style={styles.headerRow}>
        <View style={styles.statusPill}>
          <View
            style={[
              styles.dot,
              { backgroundColor: online ? theme.colors.success : theme.colors.danger },
            ]}
          />
          <Text style={styles.statusText}>
            {online ? "Online" : "Offline"}
            {status?.demo_mode ? " · Demo" : ""}
          </Text>
        </View>
        {user && (
          <View style={styles.userChip}>
            <Text style={styles.userName}>{user.name}</Text>
            {isAdmin(user.is_admin) && (
              <View style={styles.adminBadge}>
                <Text style={styles.adminText}>ADMIN</Text>
              </View>
            )}
          </View>
        )}
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      {/* Stats */}
      <View style={styles.cardRow}>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{counts?.projects ?? projects.length}</Text>
          <Text style={styles.statLabel}>Projects</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{tasks.length}</Text>
          <Text style={styles.statLabel}>Tasks</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={[styles.statValue, { color: theme.colors.warning }]}>
            {counts?.pending_approvals ?? 0}
          </Text>
          <Text style={styles.statLabel}>Approvals</Text>
        </View>
        <View style={styles.statCard}>
          <Text style={styles.statValue}>{status?.workers ?? 0}</Text>
          <Text style={styles.statLabel}>Workers</Text>
        </View>
      </View>

      {/* Task progress */}
      <Text style={styles.sectionTitle}>Task progress</Text>
      <View style={styles.card}>
        <View style={styles.progressHeader}>
          <Text style={styles.cardText}>
            {done} of {tasks.length} done
          </Text>
          <Text style={styles.pct}>{pct}%</Text>
        </View>
        <ProgressBar pct={pct} />
      </View>

      {/* Projects */}
      {projects.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Projects</Text>
          {projects.map((p) => {
            const pt = tasks.filter((t) => t.project_id === p.id);
            const pd = pt.filter((t) => TERMINAL.has(t.state)).length;
            const pp = pt.length > 0 ? Math.round((pd / pt.length) * 100) : 0;
            return (
              <View key={p.id} style={styles.card}>
                <Text style={styles.cardTitle}>{p.name}</Text>
                <View style={styles.progressHeader}>
                  <Text style={styles.cardText}>
                    {pd} of {pt.length} tasks
                  </Text>
                  <Text style={styles.pct}>{pp}%</Text>
                </View>
                <ProgressBar pct={pp} />
              </View>
            );
          })}
        </>
      )}

      {/* Agents */}
      {agents.length > 0 && (
        <>
          <Text style={styles.sectionTitle}>Agents</Text>
          {agents.map((a: AgentStatus) => (
            <View key={a.id} style={[styles.card, styles.agentCard]}>
              <View>
                <Text style={styles.cardTitle}>{a.name}</Text>
                <Text style={styles.cardText}>
                  {a.kind} · level {a.permission_level}
                </Text>
              </View>
              <View style={styles.agentStatus}>
                <View
                  style={[
                    styles.dot,
                    {
                      backgroundColor:
                        a.status === "idle" ? theme.colors.textFaint : theme.colors.primary,
                    },
                  ]}
                />
                <Text style={styles.cardText}>{a.status}</Text>
              </View>
            </View>
          ))}
        </>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  content: { padding: theme.spacing.lg, gap: theme.spacing.md },
  headerRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  statusPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.xl,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: theme.spacing.sm,
  },
  dot: { width: 8, height: 8, borderRadius: 4 },
  statusText: { color: theme.colors.text, fontWeight: "600", fontSize: 13 },
  userChip: {
    flexDirection: "row",
    alignItems: "center",
    gap: theme.spacing.sm,
  },
  userName: { color: theme.colors.textDim, fontWeight: "600", fontSize: 13 },
  adminBadge: {
    backgroundColor: theme.colors.primaryDim,
    borderRadius: theme.radius.sm,
    paddingHorizontal: theme.spacing.sm,
    paddingVertical: 2,
  },
  adminText: { color: theme.colors.primaryDark, fontSize: 10, fontWeight: "800", letterSpacing: 1 },
  error: { color: theme.colors.danger, fontSize: 13 },
  sectionTitle: {
    color: theme.colors.textDim,
    fontSize: 13,
    fontWeight: "700",
    marginTop: theme.spacing.sm,
  },
  cardRow: { flexDirection: "row", gap: theme.spacing.sm },
  statCard: {
    flex: 1,
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    alignItems: "center",
  },
  statValue: { color: theme.colors.text, fontSize: 24, fontWeight: "700" },
  statLabel: { color: theme.colors.textFaint, fontSize: 11, marginTop: 2 },
  card: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.lg,
  },
  cardTitle: { color: theme.colors.text, fontSize: 16, fontWeight: "700", marginBottom: 2 },
  cardText: { color: theme.colors.textDim, fontSize: 13 },
  progressHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginVertical: theme.spacing.sm,
  },
  pct: { color: theme.colors.primary, fontWeight: "700" },
  barTrack: {
    height: 8,
    backgroundColor: theme.colors.surfaceAlt,
    borderRadius: 4,
    overflow: "hidden",
  },
  barFill: { height: "100%", backgroundColor: theme.colors.primary, borderRadius: 4 },
  agentCard: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  agentStatus: { flexDirection: "row", alignItems: "center", gap: theme.spacing.sm },
});
