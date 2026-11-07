// ARTHUR chat — flagship screen in the muse.ai web style (dark):
// near-black canvas, "Chats" pill button, assistant replies in subtle
// dark cards with the teddy avatar, blue user bubbles, dark pill
// composer, and a slide-in drawer with chat history.

import { useEffect, useRef, useState } from "react";
import {
  Alert,
  Animated,
  FlatList,
  Image,
  KeyboardAvoidingView,
  ListRenderItemInfo,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useRouter } from "expo-router";
import { SafeAreaView } from "react-native-safe-area-context";
import { AuthError, sendChat } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import {
  Conversation,
  StoredMessage,
  createConversation,
  loadConversations,
  saveConversations,
  titleFromText,
} from "../../lib/conversations";

// muse.ai web dark palette
const BG = "#1A1A1E";
const CARD = "#26262A";
const BUBBLE = "#2E2E32";
const TEXT = "#EDEDED";
const TEXT_DIM = "#A8A8AD";
const TEXT_FAINT = "#6E6E73";
const BLUE = "#0082FB";
const LINK = "#5B9BFF";
const HAIRLINE = "#2E2E32";

const DRAWER_WIDTH = 300;
const TEDDY = require("../../assets/arthur-avatar.png");

const SUGGESTIONS = [
  { title: "Plan a new project", prompt: "Help me plan a new project" },
  { title: "Check what's waiting on me", prompt: "Check approvals" },
  { title: "Brainstorm an idea", prompt: "Brainstorm an idea with me" },
];

/** Little waveform bars, like the Meta AI suggestion icons. */
function WaveIcon({ color = TEXT_DIM }: { color?: string }) {
  const bars = [10, 18, 13, 20, 11];
  return (
    <View style={styles.wave}>
      {bars.map((h, i) => (
        <View key={i} style={[styles.waveBar, { height: h, backgroundColor: color }]} />
      ))}
    </View>
  );
}

/** Animated three-dot "ARTHUR is thinking" indicator. */
function TypingDots() {
  const dots = [
    useRef(new Animated.Value(0.3)).current,
    useRef(new Animated.Value(0.3)).current,
    useRef(new Animated.Value(0.3)).current,
  ];
  useEffect(() => {
    const anims = dots.map((v, i) =>
      Animated.loop(
        Animated.sequence([
          Animated.delay(i * 180),
          Animated.timing(v, { toValue: 1, duration: 320, useNativeDriver: true }),
          Animated.timing(v, { toValue: 0.3, duration: 320, useNativeDriver: true }),
        ]),
      ),
    );
    anims.forEach((a) => a.start());
    return () => anims.forEach((a) => a.stop());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <View style={styles.typingRow}>
      {dots.map((v, i) => (
        <Animated.View key={i} style={[styles.typingDot, { opacity: v }]} />
      ))}
    </View>
  );
}

export default function ChatScreen() {
  const router = useRouter();
  const { user } = useAuth();
  const [convos, setConvos] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [draftMsgs, setDraftMsgs] = useState<StoredMessage[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<StoredMessage>>(null);
  const drawerX = useRef(new Animated.Value(-DRAWER_WIDTH)).current;
  const backdrop = useRef(new Animated.Value(0)).current;

  const name = user?.name?.trim() || "there";

  useEffect(() => {
    void loadConversations().then(setConvos);
  }, []);

  useEffect(() => {
    void saveConversations(convos);
  }, [convos]);

  useEffect(() => {
    Animated.parallel([
      Animated.timing(drawerX, {
        toValue: drawerOpen ? 0 : -DRAWER_WIDTH,
        duration: 220,
        useNativeDriver: true,
      }),
      Animated.timing(backdrop, {
        toValue: drawerOpen ? 1 : 0,
        duration: 220,
        useNativeDriver: true,
      }),
    ]).start();
  }, [drawerOpen, drawerX, backdrop]);

  const activeConvo = activeId ? convos.find((c) => c.id === activeId) ?? null : null;
  const messages: StoredMessage[] = activeConvo ? activeConvo.messages : draftMsgs;
  const isEmpty = messages.length === 0 && !sending;

  function openDrawer() {
    setSearch("");
    setDrawerOpen(true);
  }

  function startNewChat() {
    setActiveId(null);
    setDraftMsgs([]);
    setDrawerOpen(false);
  }

  function openConvo(id: string) {
    setActiveId(id);
    setDraftMsgs([]);
    setDrawerOpen(false);
  }

  function confirmDelete(id: string, title: string) {
    Alert.alert("Delete chat?", `"${title}" will be deleted.`, [
      { text: "Cancel", style: "cancel" },
      {
        text: "Delete",
        style: "destructive",
        onPress: () => {
          setConvos((cs) => cs.filter((c) => c.id !== id));
          if (activeId === id) {
            setActiveId(null);
            setDraftMsgs([]);
          }
        },
      },
    ]);
  }

  function appendToActive(updater: (msgs: StoredMessage[]) => StoredMessage[]): {
    convoId: string;
    isNew: boolean;
  } {
    if (!activeConvo) {
      const convo = createConversation();
      convo.messages = updater(draftMsgs);
      convo.updatedAt = Date.now();
      setConvos((cs) => [convo, ...cs]);
      setActiveId(convo.id);
      setDraftMsgs([]);
      return { convoId: convo.id, isNew: true };
    }
    const id = activeConvo.id;
    setConvos((cs) =>
      cs.map((c) =>
        c.id === id
          ? { ...c, messages: updater(c.messages), updatedAt: Date.now() }
          : c,
      ),
    );
    return { convoId: id, isNew: false };
  }

  async function handleSend(raw?: string) {
    const text = (raw ?? input).trim();
    if (!text || sending) return;
    const userMsg: StoredMessage = { role: "user", content: text, ts: Date.now() };
    const { convoId, isNew } = appendToActive((msgs) => [...msgs, userMsg]);
    if (isNew) {
      setConvos((cs) =>
        cs.map((c) => (c.id === convoId ? { ...c, title: titleFromText(text) } : c)),
      );
    }
    setInput("");
    setSending(true);
    requestAnimationFrame(() => listRef.current?.scrollToEnd({ animated: true }));
    try {
      const res = await sendChat(text);
      const reply: StoredMessage = {
        role: "arthur",
        content: res.reply,
        ts: Date.now(),
        projectId: res.project_id ?? undefined,
      };
      setConvos((cs) =>
        cs.map((c) =>
          c.id === convoId
            ? { ...c, messages: [...c.messages, reply], updatedAt: Date.now() }
            : c,
        ),
      );
    } catch (err) {
      if (err instanceof AuthError) return; // AuthGate routes to login
      const failure: StoredMessage = {
        role: "arthur",
        content: `Something went wrong: ${err instanceof Error ? err.message : "request failed"}. Please try again.`,
        ts: Date.now(),
      };
      setConvos((cs) =>
        cs.map((c) =>
          c.id === convoId
            ? { ...c, messages: [...c.messages, failure], updatedAt: Date.now() }
            : c,
        ),
      );
    } finally {
      setSending(false);
    }
  }

  function renderMessage({ item }: ListRenderItemInfo<StoredMessage>) {
    if (item.role === "user") {
      return (
        <View style={styles.userRow}>
          <View style={styles.userBubble}>
            <Text style={styles.userText}>{item.content}</Text>
          </View>
        </View>
      );
    }
    return (
      <View style={styles.arthurRow}>
        <Image source={TEDDY} style={styles.arthurAvatar} resizeMode="cover" />
        <View style={styles.arthurCard}>
          <Text style={styles.arthurText}>{item.content}</Text>
          {item.projectId != null && (
            <TouchableOpacity
              style={styles.projectLink}
              onPress={() => router.push(`/projects/${item.projectId}`)}
            >
              <Text style={styles.projectLinkText}>View project →</Text>
            </TouchableOpacity>
          )}
        </View>
      </View>
    );
  }

  const q = search.trim().toLowerCase();
  const filtered = q
    ? convos.filter(
        (c) =>
          c.title.toLowerCase().includes(q) ||
          c.messages.some((m) => m.content.toLowerCase().includes(q)),
      )
    : convos;

  function renderConvo({ item }: ListRenderItemInfo<Conversation>) {
    const isActive = item.id === activeId;
    return (
      <TouchableOpacity
        style={[styles.convoRow, isActive && styles.convoRowActive]}
        onPress={() => openConvo(item.id)}
        onLongPress={() => confirmDelete(item.id, item.title)}
      >
        <Text style={styles.convoTitle} numberOfLines={1}>
          {item.title}
        </Text>
      </TouchableOpacity>
    );
  }

  const canSend = input.trim().length > 0 && !sending;

  return (
    <SafeAreaView style={styles.container} edges={["top", "bottom"]}>
      <KeyboardAvoidingView
        style={styles.flex}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {/* Top bar: "Chats" pill | new chat */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.chatsPill} onPress={openDrawer}>
            <Ionicons name="menu" size={18} color={TEXT} />
            <Text style={styles.chatsPillText}>Chats</Text>
          </TouchableOpacity>
          <View style={styles.flex} />
          <TouchableOpacity style={styles.headerBtn} onPress={startNewChat}>
            <Ionicons name="create-outline" size={22} color={TEXT} />
          </TouchableOpacity>
        </View>

        {isEmpty ? (
          <View style={styles.emptyWrap}>
            <Image source={TEDDY} style={styles.orb} resizeMode="cover" />
            <Text style={styles.emptyTitle}>What can I help with?</Text>
            <View style={styles.cards}>
              {SUGGESTIONS.map((s) => (
                <TouchableOpacity
                  key={s.title}
                  style={styles.card}
                  onPress={() => void handleSend(s.prompt)}
                >
                  <WaveIcon />
                  <Text style={styles.cardText}>{s.title}</Text>
                </TouchableOpacity>
              ))}
            </View>
          </View>
        ) : (
          <FlatList
            ref={listRef}
            data={messages}
            keyExtractor={(_, i) => String(i)}
            renderItem={renderMessage}
            contentContainerStyle={styles.list}
            onContentSizeChange={() =>
              listRef.current?.scrollToEnd({ animated: false })
            }
            ListFooterComponent={
              sending ? (
                <View style={styles.arthurRow}>
                  <Image source={TEDDY} style={styles.arthurAvatar} resizeMode="cover" />
                  <View style={styles.arthurCard}>
                    <TypingDots />
                  </View>
                </View>
              ) : null
            }
          />
        )}

        {/* Composer */}
        <View style={styles.inputWrap}>
          <View style={styles.inputBar}>
            <TextInput
              style={styles.input}
              value={input}
              onChangeText={setInput}
              placeholder="Message ARTHUR"
              placeholderTextColor={TEXT_FAINT}
              onSubmitEditing={() => void handleSend()}
              returnKeyType="send"
              multiline
              maxLength={4000}
              editable={!sending}
            />
            <TouchableOpacity
              style={[styles.sendButton, !canSend && styles.sendButtonIdle]}
              onPress={() => void handleSend()}
              disabled={!canSend}
            >
              <Ionicons
                name="arrow-up"
                size={20}
                color={canSend ? "#FFFFFF" : TEXT_FAINT}
              />
            </TouchableOpacity>
          </View>
        </View>
      </KeyboardAvoidingView>

      {/* Slide-in drawer */}
      <Animated.View
        style={[styles.backdrop, { opacity: backdrop }]}
        pointerEvents={drawerOpen ? "auto" : "none"}
      >
        <TouchableOpacity
          style={styles.flex}
          activeOpacity={1}
          onPress={() => setDrawerOpen(false)}
        />
      </Animated.View>
      <Animated.View
        style={[styles.drawer, { transform: [{ translateX: drawerX }] }]}
        pointerEvents={drawerOpen ? "auto" : "none"}
      >
        <SafeAreaView style={styles.flex} edges={["top", "bottom"]}>
          <Text style={styles.drawerTitle}>Chats</Text>
          <View style={styles.drawerSearch}>
            <Ionicons name="search" size={18} color={TEXT_FAINT} />
            <TextInput
              style={styles.drawerSearchInput}
              value={search}
              onChangeText={setSearch}
              placeholder="Search chats"
              placeholderTextColor={TEXT_FAINT}
            />
          </View>
          <TouchableOpacity style={styles.newChatRow} onPress={startNewChat}>
            <Ionicons name="create-outline" size={20} color={TEXT} />
            <Text style={styles.newChatText}>New chat</Text>
          </TouchableOpacity>
          <FlatList
            data={filtered}
            keyExtractor={(c) => c.id}
            renderItem={renderConvo}
            contentContainerStyle={styles.drawerList}
            ListEmptyComponent={
              <Text style={styles.drawerEmpty}>
                {q ? "No matches." : "No chats yet."}
              </Text>
            }
          />
          <View style={styles.drawerFooter}>
            <TouchableOpacity
              style={styles.profileRow}
              onPress={() => {
                setDrawerOpen(false);
                router.push("/settings");
              }}
            >
              <Image source={TEDDY} style={styles.profileAvatar} resizeMode="cover" />
              <Text style={styles.profileName} numberOfLines={1}>
                {name}
              </Text>
              <Ionicons name="settings-outline" size={18} color={TEXT_DIM} />
            </TouchableOpacity>
          </View>
        </SafeAreaView>
      </Animated.View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  flex: { flex: 1 },

  // Header
  header: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  chatsPill: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: CARD,
    borderRadius: 20,
    paddingVertical: 10,
    paddingHorizontal: 16,
  },
  chatsPillText: { color: TEXT, fontSize: 15, fontWeight: "600" },
  headerBtn: { width: 44, height: 44, alignItems: "center", justifyContent: "center" },

  // Empty state
  emptyWrap: {
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 28,
    paddingBottom: 48,
  },
  orb: { width: 112, height: 112, borderRadius: 56, alignSelf: "center", marginBottom: 28 },
  emptyTitle: {
    color: TEXT,
    fontSize: 26,
    fontWeight: "700",
    textAlign: "center",
    marginBottom: 24,
  },
  cards: { gap: 10 },
  card: {
    flexDirection: "row",
    alignItems: "center",
    gap: 14,
    backgroundColor: CARD,
    borderRadius: 16,
    paddingVertical: 17,
    paddingHorizontal: 20,
  },
  cardText: { color: TEXT, fontSize: 15, fontWeight: "500" },
  wave: { flexDirection: "row", alignItems: "center", gap: 3 },
  waveBar: { width: 3, borderRadius: 2 },

  // Messages
  list: { paddingVertical: 12, paddingBottom: 20 },
  userRow: {
    alignItems: "flex-end",
    paddingHorizontal: 14,
    marginVertical: 5,
  },
  userBubble: {
    backgroundColor: BLUE,
    borderRadius: 20,
    paddingVertical: 10,
    paddingHorizontal: 16,
    maxWidth: "85%",
  },
  userText: { color: "#FFFFFF", fontSize: 16, lineHeight: 24 },
  arthurRow: {
    flexDirection: "row",
    alignItems: "flex-start",
    gap: 10,
    paddingHorizontal: 14,
    paddingVertical: 6,
  },
  arthurAvatar: { width: 32, height: 32, borderRadius: 16, marginTop: 10 },
  arthurCard: {
    flex: 1,
    backgroundColor: CARD,
    borderRadius: 16,
    padding: 16,
  },
  arthurText: { color: TEXT, fontSize: 15.5, lineHeight: 24 },
  projectLink: { marginTop: 10, alignSelf: "flex-start" },
  projectLinkText: { color: LINK, fontSize: 14, fontWeight: "600" },
  typingRow: { flexDirection: "row", gap: 6, paddingVertical: 8 },
  typingDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: TEXT_FAINT },

  // Composer
  inputWrap: { paddingHorizontal: 12, paddingVertical: 10, backgroundColor: BG },
  inputBar: {
    flexDirection: "row",
    alignItems: "flex-end",
    backgroundColor: CARD,
    borderRadius: 28,
    paddingLeft: 8,
    paddingRight: 8,
    paddingVertical: 6,
    minHeight: 56,
  },
  input: {
    flex: 1,
    color: TEXT,
    fontSize: 16,
    maxHeight: 140,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  sendButton: {
    backgroundColor: BLUE,
    borderRadius: 20,
    width: 40,
    height: 40,
    alignItems: "center",
    justifyContent: "center",
  },
  sendButtonIdle: { backgroundColor: BUBBLE },

  // Drawer
  backdrop: {
    ...StyleSheet.absoluteFill,
    backgroundColor: "rgba(0,0,0,0.6)",
  },
  drawer: {
    position: "absolute",
    top: 0,
    bottom: 0,
    left: 0,
    width: DRAWER_WIDTH,
    backgroundColor: "#1E1E22",
    borderRightWidth: 1,
    borderRightColor: HAIRLINE,
  },
  drawerTitle: {
    color: TEXT,
    fontSize: 20,
    fontWeight: "700",
    paddingHorizontal: 16,
    paddingTop: 12,
    paddingBottom: 8,
  },
  drawerSearch: {
    flexDirection: "row",
    alignItems: "center",
    gap: 8,
    backgroundColor: CARD,
    borderRadius: 10,
    marginHorizontal: 12,
    marginBottom: 4,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  drawerSearchInput: { flex: 1, color: TEXT, fontSize: 15 },
  newChatRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 16,
    paddingVertical: 12,
  },
  newChatText: { color: TEXT, fontSize: 15, fontWeight: "500" },
  drawerList: { paddingHorizontal: 8, paddingBottom: 12, paddingTop: 4 },
  convoRow: { borderRadius: 10, paddingHorizontal: 12, paddingVertical: 11 },
  convoRowActive: { backgroundColor: CARD },
  convoTitle: { color: TEXT, fontSize: 15 },
  drawerEmpty: { color: TEXT_FAINT, fontSize: 14, paddingHorizontal: 16, paddingTop: 8 },
  drawerFooter: { borderTopWidth: 1, borderTopColor: HAIRLINE, padding: 8 },
  profileRow: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    paddingHorizontal: 8,
    paddingVertical: 8,
  },
  profileAvatar: { width: 36, height: 36, borderRadius: 18 },
  profileName: { flex: 1, color: TEXT, fontSize: 15, fontWeight: "500" },
});
