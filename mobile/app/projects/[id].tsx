import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  ListRenderItemInfo,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { useLocalSearchParams } from "expo-router";
import { getProjects, getTasks, type Project, type Task } from "../../lib/api";
import { theme } from "../../lib/theme";

function stateColor(state: string): string {
  switch (state) {
    case "COMPLETED":
      return theme.colors.success;
    case "FAILED":
      return theme.colors.danger;
    case "RUNNING":
      return theme.colors.primary;
    case "WAITING_FOR_APPROVAL":
      return theme.colors.warning;
    default:
      return theme.colors.textDim;
  }
}

function parseJsonList(raw: string): string[] {
  try {
    const v: unknown = JSON.parse(raw);
    return Array.isArray(v) ? v.map((x) => String(x)) : [];
  } catch {
    return [];
  }
}

export default function ProjectDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const projectId = Number(id);
  const [project, setProject] = useState<Project | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [projects, projectTasks] = await Promise.all([
        getProjects(),
        getTasks(projectId),
      ]);
      setProject(projects.find((p) => p.id === projectId) ?? null);
      setTasks(projectTasks);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load project");
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    void load();
  }, [load]);

  function renderTask({ item }: ListRenderItemInfo<Task>) {
    return (
      <View style={styles.card}>
        <View style={styles.taskHeader}>
          <Text style={styles.taskTitle}>{item.title}</Text>
          <View style={styles.statePill}>
            <Text style={[styles.stateText, { color: stateColor(item.state) }]}>
              {item.state}
            </Text>
          </View>
        </View>
        <Text style={styles.meta}>
          {item.agent} · attempt {item.attempts}/{item.max_attempts}
        </Text>
        {item.error ? <Text style={styles.taskError}>{item.error}</Text> : null}
      </View>
    );
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={theme.colors.primary} />
      </View>
    );
  }

  const conditions = project ? parseJsonList(project.completion_conditions) : [];

  return (
    <View style={styles.container}>
      {error && <Text style={styles.error}>⚠ {error}</Text>}
      <FlatList
        data={tasks}
        keyExtractor={(t) => String(t.id)}
        renderItem={renderTask}
        contentContainerStyle={styles.list}
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
        ListHeaderComponent={
          project ? (
            <View style={styles.header}>
              <Text style={styles.projectName}>{project.name}</Text>
              {project.description ? (
                <Text style={styles.projectDesc}>{project.description}</Text>
              ) : null}
              {conditions.length > 0 && (
                <View style={styles.conditions}>
                  <Text style={styles.conditionsTitle}>COMPLETION CONDITIONS</Text>
                  {conditions.map((c) => (
                    <Text key={c} style={styles.condition}>
                      • {c}
                    </Text>
                  ))}
                </View>
              )}
              <Text style={styles.sectionTitle}>TASKS</Text>
            </View>
          ) : (
            <Text style={styles.error}>Project not found.</Text>
          )
        }
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: theme.colors.background },
  center: {
    flex: 1,
    backgroundColor: theme.colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
  list: { padding: theme.spacing.lg, gap: theme.spacing.md },
  header: { marginBottom: theme.spacing.sm },
  projectName: { color: theme.colors.text, fontSize: 22, fontWeight: "800" },
  projectDesc: { color: theme.colors.textDim, fontSize: 14, marginTop: theme.spacing.sm },
  conditions: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.md,
    marginTop: theme.spacing.lg,
  },
  conditionsTitle: {
    color: theme.colors.textDim,
    fontSize: 13,
    fontWeight: "700",
    marginBottom: theme.spacing.sm,
  },
  condition: { color: theme.colors.textDim, fontSize: 13, marginBottom: 2 },
  sectionTitle: {
    color: theme.colors.textDim,
    fontSize: 13,
    fontWeight: "700",
    marginTop: theme.spacing.lg,
  },
  card: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.lg,
  },
  taskHeader: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: theme.spacing.sm,
  },
  taskTitle: { color: theme.colors.text, fontSize: 15, fontWeight: "700", flex: 1 },
  statePill: {
    backgroundColor: theme.colors.surfaceAlt,
    borderRadius: theme.radius.xl,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 4,
  },
  stateText: { fontSize: 11, fontWeight: "700" },
  meta: { color: theme.colors.textDim, fontSize: 12, marginTop: theme.spacing.xs },
  taskError: { color: theme.colors.danger, fontSize: 12, marginTop: theme.spacing.sm },
  error: { color: theme.colors.danger, fontSize: 13, padding: theme.spacing.md },
});
