"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   /staff — Staff Inbox (Real-Time WebSocket Edition)
   ─────────────────────────────────────────────────────────────────────────────
   WebSocket connection at the page root broadcasts events to conversation cards.
   Staff can reply in real-time; widget users see responses instantly.
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = API_URL.replace(/^http/, "ws");

function getAuth() {
  if (typeof window === "undefined") return { token: "", email: "", role: "", userId: "" };
  return {
    token: localStorage.getItem("token") || "",
    email: localStorage.getItem("email") || "",
    role: localStorage.getItem("role") || "staff",
    userId: localStorage.getItem("user_id") || "",
  };
}

async function apiFetch(path: string, opts: RequestInit = {}): Promise<any> {
  const { token } = getAuth();
  const res = await fetch(`${API_URL}${path}`, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(opts.headers || {}),
    },
  });
  if (res.status === 401) {
    localStorage.clear();
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  const data = await res.json();
  if (!res.ok) throw new Error(data?.detail || data?.message || `HTTP ${res.status}`);
  return data;
}

type StaffTab = "inbox" | "all";

interface Conversation {
  _id?: string;
  conv_id?: string;
  company_id: string;
  customer_id: string;
  status: string;
  assigned_staff_id: string;
  created_at: string;
  resolved_at?: string;
}

interface Message {
  msg_id?: string;
  _id?: string;
  sender_type: string;
  sender_id: string;
  content: string;
  created_at: string;
  metadata?: Record<string, any>;
}

type WsConvHandler = (event: any) => void;

/* ============================================================================= */
export default function StaffPage() {
  const router = useRouter();
  const [tab, setTab] = useState<StaffTab>("inbox");
  const [wsStatus, setWsStatus] = useState<"connecting" | "live" | "offline">("connecting");
  const [newConvCount, setNewConvCount] = useState(0);
  const { email, role } = getAuth();

  // WS infrastructure shared down to ConversationCards
  const wsRef = useRef<WebSocket | null>(null);
  // Map of conv_id → handler function registered by expanded ConversationCard
  const wsHandlers = useRef(new Map<string, WsConvHandler>());
  // Trigger to refresh the conversation list (increments on new_conversation)
  const [listRefreshKey, setListRefreshKey] = useState(0);
  const reconnectRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const auth = getAuth();
    if (!auth.token) { router.push("/login"); return; }
    if (auth.role === "superadmin") { router.push("/superadmin"); return; }
  }, [router]);

  // ── WebSocket Connection ─────────────────────────────────────────────────
  const connect = useCallback(() => {
    const { token } = getAuth();
    if (!token) return;
    const url = `${WS_URL}/api/v1/ws/staff?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => { setWsStatus("live"); };

    ws.onmessage = (evt) => {
      let data: any;
      try { data = JSON.parse(evt.data); } catch { return; }

      if (data.type === "new_conversation") {
        setNewConvCount((n) => n + 1);
        setListRefreshKey((k) => k + 1);
        return;
      }

      // Route to the correct ConversationCard handler
      const convId = data.conv_id;
      if (convId) {
        wsHandlers.current.get(convId)?.(data);
      }
    };

    ws.onerror = () => { setWsStatus("offline"); };
    ws.onclose = () => {
      setWsStatus("offline");
      wsRef.current = null;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      reconnectRef.current = setTimeout(connect, 4000);
    };
  }, []);

  useEffect(() => {
    connect();
    // Keepalive ping every 30s
    const ping = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
    return () => {
      clearInterval(ping);
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  const dashboardHref = role === "admin" ? "/dashboard" : "/login";

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#0f172a" }}>
      {/* ── Sidebar ───────────────────────────────────────────────────────── */}
      <aside style={{
        width: 220, flexShrink: 0,
        background: "#0f172a", borderRight: "1px solid #1e293b",
        padding: "20px 0", display: "flex", flexDirection: "column",
      }}>
        <div style={{ padding: "0 20px 20px", display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: "var(--primary)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 800, fontSize: 15,
          }}>R</div>
          <div>
            <p style={{ fontWeight: 700, fontSize: 16, color: "white", margin: 0 }}>ResolveAI</p>
            <p style={{ fontSize: 10, color: "#60a5fa", margin: 0, fontWeight: 600, letterSpacing: 1 }}>STAFF</p>
          </div>
        </div>

        {/* WS status dot */}
        <div style={{ padding: "0 20px 12px", display: "flex", alignItems: "center", gap: 6 }}>
          <div style={{
            width: 7, height: 7, borderRadius: "50%",
            background: wsStatus === "live" ? "#4ade80"
              : wsStatus === "connecting" ? "#fbbf24" : "#f87171",
          }} />
          <span style={{ fontSize: 11, color: wsStatus === "live" ? "#4ade80" : "#64748b" }}>
            {wsStatus === "live" ? "Live" : wsStatus === "connecting" ? "Connecting…" : "Reconnecting…"}
          </span>
        </div>

        {role !== "staff" && (
          <div style={{ padding: "0 20px 16px" }}>
            <a href={dashboardHref} style={{
              display: "flex", alignItems: "center", gap: 6,
              color: "#475569", textDecoration: "none", fontSize: 12,
              padding: "6px 8px", borderRadius: 6,
            }}>← Back to Dashboard</a>
          </div>
        )}

        <div style={{ height: 1, background: "#1e293b", margin: "0 20px 16px" }} />

        <nav style={{ flex: 1 }}>
          {([
            { key: "inbox", label: "My Inbox", icon: "📬" },
            { key: "all",   label: "All Conversations", icon: "💬" },
          ] as const).map((t) => (
            <button key={t.key} onClick={() => { setTab(t.key); if (t.key === "all") setNewConvCount(0); }} style={{
              display: "flex", alignItems: "center", gap: 10,
              width: "100%", padding: "10px 20px", border: "none",
              background: tab === t.key ? "rgba(96,165,250,0.1)" : "transparent",
              color: tab === t.key ? "#60a5fa" : "#64748b",
              fontWeight: tab === t.key ? 600 : 400,
              fontSize: 14, cursor: "pointer",
              borderLeft: tab === t.key ? "3px solid #60a5fa" : "3px solid transparent",
              fontFamily: "inherit", transition: "all 0.15s",
              justifyContent: "space-between",
            }}>
              <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <span style={{ fontSize: 16 }}>{t.icon}</span>
                {t.label}
              </span>
              {t.key === "all" && newConvCount > 0 && (
                <span style={{
                  background: "#ef4444", color: "white",
                  borderRadius: "50%", width: 18, height: 18,
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 10, fontWeight: 700,
                }}>{newConvCount > 9 ? "9+" : newConvCount}</span>
              )}
            </button>
          ))}
        </nav>

        <div style={{ padding: "16px 20px", borderTop: "1px solid #1e293b" }}>
          <p style={{ fontSize: 12, color: "#334155", marginBottom: 4 }}>{email}</p>
          <p style={{ fontSize: 11, color: "#1e40af", background: "#dbeafe", display: "inline-block", padding: "2px 8px", borderRadius: 4, marginBottom: 8 }}>
            {role}
          </p><br />
          <button
            onClick={() => { localStorage.clear(); router.push("/login"); }}
            style={{ background: "none", border: "none", color: "#475569", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}
          >Sign Out</button>
        </div>
      </aside>

      {/* ── Main ──────────────────────────────────────────────────────────── */}
      <main style={{ flex: 1, background: "#f8fafc", padding: 32, overflowY: "auto", minWidth: 0 }}>
        {tab === "inbox" && (
          <ConversationsTab
            filterAssigned
            wsRef={wsRef}
            wsHandlers={wsHandlers}
            refreshKey={listRefreshKey}
          />
        )}
        {tab === "all" && (
          <ConversationsTab
            wsRef={wsRef}
            wsHandlers={wsHandlers}
            refreshKey={listRefreshKey}
          />
        )}
      </main>
    </div>
  );
}

/* ============================================================================= */
/* Conversations Tab                                                               */
/* ============================================================================= */
function ConversationsTab({
  filterAssigned = false,
  wsRef,
  wsHandlers,
  refreshKey,
}: {
  filterAssigned?: boolean;
  wsRef: React.RefObject<WebSocket | null>;
  wsHandlers: React.RefObject<Map<string, WsConvHandler>>;
  refreshKey: number;
}) {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [statusFilter, setStatusFilter] = useState<string>("active");
  const [loading, setLoading] = useState(true);

  const loadConversations = useCallback(() => {
    setLoading(true);
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    apiFetch(`/api/v1/conversations${qs}`)
      .then((d) => {
        let convs = d.conversations || [];
        if (filterAssigned) {
          const { userId } = getAuth();
          convs = convs.filter((c: Conversation) => c.assigned_staff_id === userId);
        }
        setConversations(convs);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [statusFilter, filterAssigned]);

  // Re-load when filter changes or when WS signals new conversation
  useEffect(() => { loadConversations(); }, [loadConversations, refreshKey]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>
            {filterAssigned ? "My Inbox" : "All Conversations"}
          </h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>
            {conversations.length} conversation{conversations.length !== 1 ? "s" : ""}
          </p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["active", "resolved", "all"].map((s) => (
            <button key={s} onClick={() => setStatusFilter(s === "all" ? "" : s)} style={{
              padding: "7px 14px", borderRadius: 8, border: "1px solid var(--slate-200)",
              background: (statusFilter === s || (s === "all" && !statusFilter)) ? "var(--primary)" : "white",
              color: (statusFilter === s || (s === "all" && !statusFilter)) ? "white" : "var(--slate-600)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              fontWeight: (statusFilter === s || (s === "all" && !statusFilter)) ? 600 : 400,
            }}>
              {s === "active" ? "Active" : s === "resolved" ? "Resolved" : "All"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p style={{ color: "var(--slate-400)", fontSize: 14 }}>Loading…</p>
      ) : conversations.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p style={{ fontSize: 28, marginBottom: 8 }}>📭</p>
          <p style={{ color: "var(--slate-500)", fontSize: 14 }}>
            {filterAssigned ? "No conversations assigned to you." : "No conversations found."}
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {conversations.map((c) => (
            <ConversationCard
              key={c._id || c.conv_id}
              conversation={c}
              wsRef={wsRef}
              wsHandlers={wsHandlers}
              onUpdate={loadConversations}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Conversation Card (expandable, real-time)                                       */
/* ============================================================================= */
function ConversationCard({
  conversation,
  wsRef,
  wsHandlers,
  onUpdate,
}: {
  conversation: Conversation;
  wsRef: React.RefObject<WebSocket | null>;
  wsHandlers: React.RefObject<Map<string, WsConvHandler>>;
  onUpdate: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [showResolveModal, setShowResolveModal] = useState(false);
  const [convStatus, setConvStatus] = useState(conversation.status);
  const [typingLabel, setTypingLabel] = useState<string | null>(null);
  const [hasUnread, setHasUnread] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const typingTimerRef = useRef<NodeJS.Timeout | null>(null);

  const convId = conversation._id || conversation.conv_id || "";

  // Sync convStatus when prop changes (e.g. list refresh)
  useEffect(() => { setConvStatus(conversation.status); }, [conversation.status]);

  // ── Load messages via REST on expand ──────────────────────────────────────
  const loadMessages = useCallback(() => {
    apiFetch(`/api/v1/conversations/${convId}`)
      .then((d) => setMessages(d.messages || []))
      .catch(console.error);
  }, [convId]);

  // ── Subscribe to WS room on expand, unsubscribe on collapse ──────────────
  useEffect(() => {
    if (!expanded || !convId) return;

    loadMessages();

    // Subscribe to WS conversation room
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "join", conv_id: convId }));
    }

    // Register handler for real-time events on this conversation
    const handler = (event: any) => {
      if (event.type === "message" || event.type === "message_ack") {
        setMessages((prev) => {
          const id = event.msg_id;
          if (id && prev.some((m) => (m.msg_id || m._id) === id)) return prev;
          return [...prev, {
            msg_id: event.msg_id,
            sender_type: event.sender_type,
            sender_id: event.sender_id,
            content: event.content,
            created_at: event.created_at,
            metadata: event.metadata,
          }];
        });
      } else if (event.type === "conversation_history") {
        setMessages(event.messages || []);
      } else if (event.type === "typing") {
        if (event.sender_type === "customer") {
          if (event.is_typing) {
            setTypingLabel("Customer");
            if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
            typingTimerRef.current = setTimeout(() => setTypingLabel(null), 4000);
          } else {
            setTypingLabel(null);
          }
        }
      } else if (event.type === "conversation_status") {
        setConvStatus(event.new_status);
        onUpdate();
      }
    };
    wsHandlers.current?.set(convId, handler);

    return () => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "leave", conv_id: convId }));
      }
      wsHandlers.current?.delete(convId);
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
    };
  }, [expanded, convId]);

  // Show unread badge for new messages not yet expanded
  useEffect(() => {
    if (!expanded) return;
    setHasUnread(false);
  }, [expanded]);

  // Detect incoming messages while collapsed
  useEffect(() => {
    if (expanded) return;
    const existingHandler = wsHandlers.current?.get(convId);
    if (existingHandler) return;
    const peekHandler = (event: any) => {
      if (event.type === "message") setHasUnread(true);
    };
    wsHandlers.current?.set(convId, peekHandler);
    return () => { wsHandlers.current?.delete(convId); };
  }, [expanded, convId]);

  // Auto-scroll
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, typingLabel]);

  // ── Send reply ─────────────────────────────────────────────────────────────
  const sendReply = async () => {
    if (!reply.trim() || sending) return;
    setSending(true);
    const content = reply.trim();

    // Prefer WebSocket for instant delivery
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "message", conv_id: convId, content }));
      setReply("");
      setSending(false);
    } else {
      // Fallback to REST
      try {
        await apiFetch(`/api/v1/conversations/${convId}/message`, {
          method: "POST",
          body: JSON.stringify({ content }),
        });
        setReply("");
        loadMessages();
      } catch (err) { console.error(err); }
      setSending(false);
    }
  };

  const handleReplyChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setReply(e.target.value);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: "typing", conv_id: convId, is_typing: e.target.value.length > 0,
      }));
    }
  };

  const handleEscalate = async () => {
    if (!confirm("Escalate this conversation? It will be unassigned.")) return;
    try {
      await apiFetch(`/api/v1/conversations/${convId}/escalate`, { method: "POST" });
      onUpdate();
    } catch (err) { console.error(err); }
  };

  const statusColors: Record<string, { bg: string; color: string }> = {
    active:   { bg: "#dcfce7", color: "#166534" },
    resolved: { bg: "#dbeafe", color: "#1e40af" },
    archived: { bg: "#f1f5f9", color: "#475569" },
  };
  const sc = statusColors[convStatus] || statusColors.archived;

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      {/* Header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: expanded ? 16 : 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 11, padding: "3px 9px", borderRadius: 4, fontWeight: 600, background: sc.bg, color: sc.color }}>
            {convStatus}
          </span>
          <span style={{ fontSize: 12, color: "var(--slate-500)", fontFamily: "monospace" }}>
            #{convId.slice(-8)}
          </span>
          <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
            · {conversation.customer_id.slice(0, 16)}…
          </span>
          {hasUnread && !expanded && (
            <span style={{
              background: "#ef4444", color: "white",
              borderRadius: 4, padding: "1px 6px", fontSize: 10, fontWeight: 700,
            }}>NEW</span>
          )}
        </div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
            {new Date(conversation.created_at).toLocaleString()}
          </span>
          <button
            onClick={() => setExpanded(!expanded)}
            style={{
              padding: "5px 12px", borderRadius: 6,
              border: "1px solid var(--slate-200)", background: "white",
              color: "var(--slate-600)", fontSize: 12, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            {expanded ? "Collapse" : "Open"}
          </button>
        </div>
      </div>

      {/* Expanded: messages + reply */}
      {expanded && (
        <div>
          {/* Message thread */}
          <div style={{
            background: "var(--slate-50)", borderRadius: 10, padding: 16,
            maxHeight: 360, overflowY: "auto", marginBottom: 12,
            display: "flex", flexDirection: "column", gap: 10,
          }}>
            {messages.length === 0 && (
              <p style={{ color: "var(--slate-400)", fontSize: 13, textAlign: "center" }}>No messages yet.</p>
            )}
            {messages.map((msg, i) => {
              const id = msg.msg_id || msg._id || i.toString();
              const isCustomer = msg.sender_type === "customer";
              const isAI = msg.sender_type === "ai";
              return (
                <div key={id} style={{ display: "flex", justifyContent: isCustomer ? "flex-end" : "flex-start" }}>
                  <div style={{ maxWidth: "75%" }}>
                    <p style={{ fontSize: 11, color: "var(--slate-400)", marginBottom: 3, textAlign: isCustomer ? "right" : "left" }}>
                      {isAI ? "AI" : isCustomer ? "Customer" : msg.sender_type}
                      {" · "}{msg.created_at ? new Date(msg.created_at).toLocaleTimeString() : ""}
                    </p>
                    <div style={{
                      padding: "10px 14px",
                      borderRadius: isCustomer ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                      background: isCustomer ? "var(--primary)" : isAI ? "#f0fdf4" : "white",
                      color: isCustomer ? "white" : isAI ? "#166534" : "var(--slate-800)",
                      fontSize: 13, lineHeight: 1.5,
                      border: isAI ? "1px solid #bbf7d0" : isCustomer ? "none" : "1px solid var(--slate-200)",
                    }}>
                      {msg.content}
                    </div>
                    {isAI && msg.metadata?.action && (
                      <div style={{ marginTop: 4 }}>
                        <span style={{
                          fontSize: 10, padding: "2px 8px", borderRadius: 4, fontWeight: 600,
                          background: msg.metadata.action === "escalate" ? "#fee2e2" : "#dcfce7",
                          color: msg.metadata.action === "escalate" ? "#991b1b" : "#166534",
                        }}>
                          AI: {msg.metadata.action}
                          {msg.metadata.confidence ? ` (${(msg.metadata.confidence * 100).toFixed(0)}%)` : ""}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* Typing indicator */}
            {typingLabel && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <div style={{ display: "flex", gap: 4, padding: "8px 14px", background: "#f1f5f9", borderRadius: "18px 18px 18px 4px", border: "1px solid var(--slate-200)" }}>
                  {[0, 1, 2].map((i) => (
                    <span key={i} style={{
                      width: 5, height: 5, borderRadius: "50%", background: "#94a3b8",
                      display: "inline-block", opacity: 0.7,
                    }} />
                  ))}
                </div>
                <span style={{ fontSize: 11, color: "var(--slate-400)" }}>{typingLabel} is typing…</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Reply + actions */}
          {convStatus === "active" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              <div style={{ display: "flex", gap: 8 }}>
                <textarea
                  className="input"
                  rows={2}
                  placeholder="Type your reply… (Ctrl+Enter to send)"
                  value={reply}
                  onChange={handleReplyChange}
                  onKeyDown={(e) => { if (e.key === "Enter" && e.ctrlKey) sendReply(); }}
                  style={{ flex: 1, resize: "none", fontFamily: "inherit", fontSize: 13 }}
                />
                <button
                  className="btn btn-primary"
                  onClick={sendReply}
                  disabled={sending || !reply.trim()}
                  style={{ alignSelf: "flex-end", padding: "8px 18px", fontSize: 13 }}
                >
                  {sending ? "…" : "Send"}
                </button>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button onClick={() => setShowResolveModal(true)} style={{
                  padding: "8px 16px", borderRadius: 8,
                  border: "1px solid #bbf7d0", background: "#f0fdf4",
                  color: "#166534", fontSize: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
                }}>Resolve & Ingest to KB</button>
                <button onClick={handleEscalate} style={{
                  padding: "8px 16px", borderRadius: 8,
                  border: "1px solid #fecaca", background: "#fef2f2",
                  color: "#dc2626", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
                }}>Escalate</button>
              </div>
            </div>
          )}

          {convStatus !== "active" && (
            <p style={{ fontSize: 12, color: "var(--slate-400)", textAlign: "center", padding: "8px 0" }}>
              This conversation is {convStatus}.
            </p>
          )}
        </div>
      )}

      {/* Resolve Modal */}
      {showResolveModal && (
        <ResolveModal
          convId={convId}
          messages={messages}
          onClose={() => setShowResolveModal(false)}
          onResolved={() => { setShowResolveModal(false); onUpdate(); }}
        />
      )}
    </div>
  );
}

/* ============================================================================= */
/* Resolve Modal                                                                   */
/* ============================================================================= */
function ResolveModal({
  convId, messages, onClose, onResolved,
}: {
  convId: string;
  messages: Message[];
  onClose: () => void;
  onResolved: () => void;
}) {
  const lastAI = [...messages].reverse().find((m) => m.sender_type === "ai");
  const customerMessages = messages.filter((m) => m.sender_type === "customer");
  const question = customerMessages[0]?.content || "";

  // If the last AI message was an escalation, don't pre-fill — staff must write the real answer
  const isEscalation = lastAI?.metadata?.action === "escalate" || !lastAI;
  const [title, setTitle] = useState(question.slice(0, 80));
  const [canonicalAnswer, setCanonicalAnswer] = useState(isEscalation ? "" : (lastAI?.content || ""));
  const [tags, setTags] = useState("");
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState("");
  const [result, setResult] = useState<{ chunks: number } | null>(null);

  const handleResolve = async () => {
    if (!canonicalAnswer.trim()) return;
    setResolving(true); setError("");
    try {
      const data = await apiFetch(`/api/v1/conversations/${convId}/resolve`, {
        method: "POST",
        body: JSON.stringify({ canonical_answer: canonicalAnswer, title: title || question.slice(0, 80), tags }),
      });
      setResult({ chunks: data.chunks_ingested ?? 0 });
      setTimeout(() => { onResolved(); }, 1800);
    } catch (err: any) { setError(err.message || "Failed to resolve"); }
    setResolving(false);
  };

  return (
    <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 24 }}>
      <div className="card" style={{ width: 560, padding: 32, maxHeight: "90vh", overflowY: "auto" }}>
        <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Resolve & Ingest to KB</h2>
        <p style={{ fontSize: 13, color: "var(--slate-500)", marginBottom: 24 }}>
          Verify the canonical answer before it's embedded into the knowledge base.
        </p>

        {result ? (
          <div style={{ background: "#f0fdf4", color: "#166534", padding: "16px", borderRadius: 8, border: "1px solid #bbf7d0", textAlign: "center" }}>
            <p style={{ fontWeight: 700, fontSize: 15, marginBottom: 4 }}>Resolved & Ingested</p>
            <p style={{ fontSize: 13 }}>{result.chunks} chunk{result.chunks !== 1 ? "s" : ""} embedded into KB</p>
          </div>
        ) : (
          <>
            {error && <div style={{ background: "#fef2f2", color: "#dc2626", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16, border: "1px solid #fecaca" }}>{error}</div>}
            {isEscalation && (
              <div style={{ background: "#fffbeb", color: "#92400e", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16, border: "1px solid #fde68a" }}>
                The AI escalated this conversation. Write the correct answer below — it will be learned by the KB.
              </div>
            )}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>KB Entry Title</label>
              <input className="input" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Brief title for knowledge base entry" />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>
                Canonical Answer <span style={{ color: "var(--slate-400)", fontWeight: 400 }}>(will be embedded)</span>
              </label>
              <textarea className="input" rows={5} value={canonicalAnswer} onChange={(e) => setCanonicalAnswer(e.target.value)} placeholder="The definitive answer that should be learned by the AI…" style={{ resize: "vertical", fontFamily: "inherit" }} required />
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>Tags (optional)</label>
              <input className="input" value={tags} onChange={(e) => setTags(e.target.value)} placeholder="billing, account, password" />
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={onClose} style={{ padding: "10px 20px", borderRadius: 8, border: "1px solid var(--slate-200)", background: "white", color: "var(--slate-600)", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}>Cancel</button>
              <button className="btn btn-primary" onClick={handleResolve} disabled={resolving || !canonicalAnswer.trim()} style={{ padding: "10px 20px", fontSize: 13 }}>
                {resolving ? "Resolving…" : "Resolve & Ingest"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
