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
import { getApprovals, resolveApproval, type Approval } from "../../lib/api";
import { timeAgo } from "../../lib/format";
import { theme } from "../../lib/theme";

export default function ApprovalsScreen() {
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [resolving, setResolving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setApprovals(await getApprovals());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load approvals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleResolve(id: number, approved: boolean) {
    setResolving(id);
    try {
      await resolveApproval(id, approved);
      setApprovals((list) => list.filter((a) => a.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Resolve failed");
    } finally {
      setResolving(null);
    }
  }

  function renderItem({ item }: ListRenderItemInfo<Approval>) {
    const busy = resolving === item.id;
    return (
      <View style={styles.card}>
        <View style={styles.kindRow}>
          <View style={styles.kindPill}>
            <Text style={styles.kind}>{item.kind}</Text>
          </View>
          <Text style={styles.time}>{timeAgo(item.created_at)}</Text>
        </View>
        <Text style={styles.subject}>{item.subject}</Text>
        {item.requested_by ? (
          <Text style={styles.meta}>requested by {item.requested_by}</Text>
        ) : null}
        <View style={styles.actions}>
          <TouchableOpacity
            style={[styles.button, styles.approve]}
            disabled={busy}
            onPress={() => void handleResolve(item.id, true)}
          >
            {busy ? (
              <ActivityIndicator color="#FFFFFF" />
            ) : (
              <Text style={styles.approveText}>Approve</Text>
            )}
          </TouchableOpacity>
          <TouchableOpacity
            style={[styles.button, styles.deny]}
            disabled={busy}
            onPress={() => void handleResolve(item.id, false)}
          >
            <Text style={styles.denyText}>Deny</Text>
          </TouchableOpacity>
        </View>
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

  return (
    <View style={styles.container}>
      {error && <Text style={styles.error}>{error}</Text>}
      <FlatList
        data={approvals}
        keyExtractor={(a) => String(a.id)}
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
            <Text style={styles.emptyTitle}>All clear</Text>
            <Text style={styles.emptySub}>No pending approvals right now.</Text>
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
  kindRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
    marginBottom: theme.spacing.sm,
  },
  kindPill: {
    backgroundColor: theme.colors.surfaceAlt,
    borderRadius: theme.radius.xl,
    paddingHorizontal: theme.spacing.md,
    paddingVertical: 4,
  },
  kind: {
    color: theme.colors.textDim,
    fontSize: 11,
    fontWeight: "700",
  },
  time: { color: theme.colors.textFaint, fontSize: 11 },
  subject: { color: theme.colors.text, fontSize: 15, fontWeight: "600", lineHeight: 22 },
  meta: { color: theme.colors.textFaint, fontSize: 12, marginTop: theme.spacing.xs },
  actions: { flexDirection: "row", gap: theme.spacing.sm, marginTop: theme.spacing.lg },
  button: {
    flex: 1,
    borderRadius: theme.radius.xl,
    paddingVertical: theme.spacing.md,
    alignItems: "center",
  },
  approve: { backgroundColor: theme.colors.primary },
  approveText: { color: "#FFFFFF", fontWeight: "700", fontSize: 14 },
  deny: {
    backgroundColor: "transparent",
    borderWidth: 1,
    borderColor: theme.colors.border,
  },
  denyText: { color: theme.colors.textDim, fontWeight: "700", fontSize: 14 },
  error: { color: theme.colors.danger, fontSize: 13, padding: theme.spacing.md },
  emptyWrap: { alignItems: "center", marginTop: theme.spacing.xxl * 2, gap: 6 },
  emptyTitle: { color: theme.colors.text, fontSize: 18, fontWeight: "700" },
  emptySub: { color: theme.colors.textFaint, fontSize: 14 },
});
