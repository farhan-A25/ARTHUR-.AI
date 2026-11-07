import { useCallback, useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  ListRenderItemInfo,
  RefreshControl,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { getProjects, type Project } from "../../lib/api";
import { timeAgo } from "../../lib/format";
import { theme } from "../../lib/theme";

export default function ProjectsScreen() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setProjects(await getProjects());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  function renderItem({ item }: ListRenderItemInfo<Project>) {
    return (
      <TouchableOpacity
        style={styles.card}
        onPress={() => router.push(`/projects/${item.id}`)}
      >
        <View style={styles.row}>
          <View style={styles.textCol}>
            <Text style={styles.name}>{item.name}</Text>
            {item.description ? (
              <Text style={styles.desc} numberOfLines={2}>
                {item.description}
              </Text>
            ) : null}
            <View style={styles.metaRow}>
              <Text style={styles.meta}>{item.status}</Text>
              <Text style={styles.dot}>·</Text>
              <Text style={styles.time}>{timeAgo(item.updated_at)}</Text>
            </View>
          </View>
          <Ionicons name="chevron-forward" size={20} color={theme.colors.textFaint} />
        </View>
      </TouchableOpacity>
    );
  }

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator color={theme.colors.primary} />
      </View>
    );
  }

  return (
    <View style={styles.container}>
      {error && <Text style={styles.error}>{error}</Text>}
      <FlatList
        data={projects}
        keyExtractor={(p) => String(p.id)}
        renderItem={renderItem}
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
        ListEmptyComponent={
          <View style={styles.emptyWrap}>
            <Text style={styles.emptyTitle}>No projects yet</Text>
            <Text style={styles.emptySub}>Give ARTHUR a goal in Chat.</Text>
          </View>
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
  card: {
    backgroundColor: theme.colors.surface,
    borderWidth: 1,
    borderColor: theme.colors.border,
    borderRadius: theme.radius.md,
    padding: theme.spacing.lg,
  },
  row: { flexDirection: "row", alignItems: "center", gap: theme.spacing.md },
  textCol: { flex: 1, gap: 4 },
  name: { color: theme.colors.text, fontSize: 16, fontWeight: "700" },
  desc: { color: theme.colors.textDim, fontSize: 13, lineHeight: 19 },
  metaRow: { flexDirection: "row", alignItems: "center", gap: 6, marginTop: 2 },
  meta: { color: theme.colors.primary, fontSize: 12, fontWeight: "600" },
  dot: { color: theme.colors.textFaint, fontSize: 12 },
  time: { color: theme.colors.textFaint, fontSize: 12 },
  error: { color: theme.colors.danger, fontSize: 13, padding: theme.spacing.md },
  emptyWrap: { alignItems: "center", marginTop: theme.spacing.xxl * 2, gap: 6 },
  emptyTitle: { color: theme.colors.text, fontSize: 18, fontWeight: "700" },
  emptySub: { color: theme.colors.textFaint, fontSize: 14 },
});
