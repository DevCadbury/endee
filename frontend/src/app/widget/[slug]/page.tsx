"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams } from "next/navigation";

/* =============================================================================
   /widget/[slug] — Embeddable Customer Chat Widget
   ─────────────────────────────────────────────────────────────────────────────
   Connects to the ResolveAI backend via WebSocket.
   Session ID is persisted in localStorage so conversations resume on reload.
   Can be loaded directly or embedded in an <iframe>.
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_URL = API_URL.replace(/^http/, "ws");

// ── Session helpers ──────────────────────────────────────────────────────────

function getSessionId(slug: string): string {
  const key = `widget_session_${slug}`;
  let id = localStorage.getItem(key);
  if (!id) {
    id = "ws_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
    localStorage.setItem(key, id);
  }
  return id;
}

function getPersistedConvId(slug: string): string | null {
  return localStorage.getItem(`widget_conv_${slug}`);
}

function setPersistedConvId(slug: string, convId: string) {
  localStorage.setItem(`widget_conv_${slug}`, convId);
}

function clearPersistedConvId(slug: string) {
  localStorage.removeItem(`widget_conv_${slug}`);
}

// ── Types ────────────────────────────────────────────────────────────────────

interface WsMessage {
  msg_id?: string;
  sender_type: string;   // customer | ai | staff | admin
  sender_id?: string;
  content: string;
  created_at?: string;
  metadata?: Record<string, any>;
}

// ── Message bubble ───────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: WsMessage }) {
  const isCustomer = msg.sender_type === "customer";
  const isAI = msg.sender_type === "ai";
  const isStaff = msg.sender_type === "staff" || msg.sender_type === "admin";

  const label = isCustomer ? "You"
    : isAI ? "AI Assistant"
    : "Support Agent";

  return (
    <div style={{ display: "flex", justifyContent: isCustomer ? "flex-end" : "flex-start", marginBottom: 12 }}>
      {!isCustomer && (
        <div style={{
          width: 28, height: 28, borderRadius: "50%", flexShrink: 0,
          background: isAI ? "#dcfce7" : "#dbeafe",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: 12, fontWeight: 700, color: isAI ? "#166534" : "#1e40af",
          marginRight: 8, marginTop: 2,
        }}>
          {isAI ? "AI" : "SU"}
        </div>
      )}
      <div style={{ maxWidth: "80%" }}>
        <p style={{ fontSize: 10, color: "#94a3b8", marginBottom: 3, textAlign: isCustomer ? "right" : "left" }}>
          {label}
          {msg.created_at && " · " + new Date(msg.created_at).toLocaleTimeString()}
        </p>
        <div style={{
          padding: "10px 14px",
          borderRadius: isCustomer ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
          background: isCustomer ? "#16a34a" : isAI ? "#f0fdf4" : "#eff6ff",
          color: isCustomer ? "#fff" : isAI ? "#166534" : "#1e3a5f",
          fontSize: 13, lineHeight: 1.55,
          border: isCustomer ? "none"
            : isAI ? "1px solid #bbf7d0"
            : "1px solid #bfdbfe",
          boxShadow: "0 1px 2px rgba(0,0,0,0.06)",
          wordBreak: "break-word",
        }}>
          {msg.content}
        </div>
        {isAI && msg.metadata?.action === "escalate" && (
          <p style={{ fontSize: 10, color: "#f59e0b", marginTop: 3 }}>
            Connecting you with a support agent…
          </p>
        )}
      </div>
    </div>
  );
}

// ── Typing indicator ─────────────────────────────────────────────────────────

function TypingIndicator({ label }: { label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <div style={{
        width: 28, height: 28, borderRadius: "50%",
        background: "#dbeafe", display: "flex", alignItems: "center",
        justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#1e40af",
      }}>SU</div>
      <div style={{
        padding: "8px 14px", borderRadius: "18px 18px 18px 4px",
        background: "#f1f5f9", border: "1px solid #e2e8f0",
        display: "flex", gap: 4, alignItems: "center",
      }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{
            width: 6, height: 6, borderRadius: "50%", background: "#94a3b8",
            display: "inline-block",
            animation: "bounce 1.2s ease-in-out infinite",
            animationDelay: `${i * 0.2}s`,
          }} />
        ))}
      </div>
      <span style={{ fontSize: 11, color: "#94a3b8" }}>{label} is typing...</span>
    </div>
  );
}

// ── AI thinking indicator ────────────────────────────────────────────────────

function ThinkingIndicator() {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
      <div style={{
        width: 28, height: 28, borderRadius: "50%",
        background: "#dcfce7", display: "flex", alignItems: "center",
        justifyContent: "center", fontSize: 12, fontWeight: 700, color: "#166534",
      }}>AI</div>
      <div style={{
        padding: "8px 14px", borderRadius: "18px 18px 18px 4px",
        background: "#f0fdf4", border: "1px solid #bbf7d0",
        display: "flex", gap: 4, alignItems: "center",
      }}>
        {[0, 1, 2].map((i) => (
          <span key={i} style={{
            width: 6, height: 6, borderRadius: "50%", background: "#86efac",
            display: "inline-block",
            animation: "bounce 1.2s ease-in-out infinite",
            animationDelay: `${i * 0.2}s`,
          }} />
        ))}
      </div>
      <span style={{ fontSize: 11, color: "#86efac" }}>AI is thinking...</span>
    </div>
  );
}

// ── Main Widget Component ────────────────────────────────────────────────────

export default function WidgetPage() {
  const params = useParams();
  const slug = Array.isArray(params.slug) ? params.slug[0] : (params.slug as string);

  const [messages, setMessages] = useState<WsMessage[]>([]);
  const [input, setInput] = useState("");
  const [convId, setConvId] = useState<string | null>(null);
  const [convStatus, setConvStatus] = useState<"active" | "resolved">("active");
  const [wsStatus, setWsStatus] = useState<"connecting" | "connected" | "error" | "closed">("connecting");
  const [isThinking, setIsThinking] = useState(false);
  const [typingFrom, setTypingFrom] = useState<string | null>(null);   // "agent" | "agent (admin)"
  const [staffOnline, setStaffOnline] = useState(false);

  const wsRef = useRef<WebSocket | null>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const typingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const sessionIdRef = useRef<string>("");

  // ── Scroll to bottom on new message ───────────────────────────────────────
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isThinking, typingFrom]);

  // ── Build WS URL ───────────────────────────────────────────────────────────
  const buildWsUrl = useCallback(() => {
    const sessionId = sessionIdRef.current;
    const persistedConv = getPersistedConvId(slug);
    let url = `${WS_URL}/api/v1/ws/widget/${slug}?session_id=${encodeURIComponent(sessionId)}`;
    if (persistedConv) url += `&conv_id=${encodeURIComponent(persistedConv)}`;
    return url;
  }, [slug]);

  // ── Connect / Reconnect ───────────────────────────────────────────────────
  const connect = useCallback(() => {
    if (!slug) return;
    const url = buildWsUrl();
    const ws = new WebSocket(url);
    wsRef.current = ws;
    setWsStatus("connecting");

    ws.onopen = () => {
      setWsStatus("connected");
    };

    ws.onmessage = (evt) => {
      let data: any;
      try { data = JSON.parse(evt.data); } catch { return; }

      switch (data.type) {
        case "connected": {
          setConvId(data.conv_id);
          setPersistedConvId(slug, data.conv_id);
          setStaffOnline((data.staff_online ?? 0) > 0);
          // Hydrate history
          if (Array.isArray(data.messages)) {
            setMessages(data.messages.map((m: any) => ({
              msg_id: m._id || m.msg_id,
              sender_type: m.sender_type,
              sender_id: m.sender_id,
              content: m.content,
              created_at: m.created_at,
              metadata: m.metadata,
            })));
          }
          break;
        }
        case "message":
        case "message_ack": {
          setIsThinking(false);
          setMessages((prev) => {
            // Avoid duplicates (message_ack echoes back to sender)
            const exists = prev.some((m) => m.msg_id && m.msg_id === data.msg_id);
            if (exists) return prev;
            return [...prev, {
              msg_id: data.msg_id,
              sender_type: data.sender_type,
              sender_id: data.sender_id,
              content: data.content,
              created_at: data.created_at,
              metadata: data.metadata,
            }];
          });
          break;
        }
        case "ai_thinking": {
          setIsThinking(true);
          break;
        }
        case "typing": {
          const senderType = data.sender_type;
          if (senderType === "staff" || senderType === "admin") {
            const label = senderType === "admin" ? "Agent (Admin)" : "Agent";
            if (data.is_typing) {
              setTypingFrom(label);
              if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
              typingTimerRef.current = setTimeout(() => setTypingFrom(null), 4000);
            } else {
              setTypingFrom(null);
            }
          }
          break;
        }
        case "conversation_status": {
          if (data.new_status === "resolved") {
            setConvStatus("resolved");
            setIsThinking(false);
            setTypingFrom(null);
          }
          break;
        }
        case "presence": {
          if (data.role === "staff" || data.role === "admin") {
            setStaffOnline(data.event === "joined");
          }
          break;
        }
        case "error": {
          if (data.code === "conversation_resolved") {
            setConvStatus("resolved");
          }
          break;
        }
        case "pong":
          break;
      }
    };

    ws.onerror = () => { setWsStatus("error"); };

    ws.onclose = () => {
      setWsStatus("closed");
      wsRef.current = null;
      // Reconnect after 3 seconds
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = setTimeout(connect, 3000);
    };

    return () => { ws.close(); };
  }, [slug, buildWsUrl]);

  // ── Initialize ─────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!slug) return;
    sessionIdRef.current = getSessionId(slug);
    const cleanup = connect();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (typingTimerRef.current) clearTimeout(typingTimerRef.current);
      wsRef.current?.close();
    };
  }, [slug]);

  // ── Ping / keepalive ───────────────────────────────────────────────────────
  useEffect(() => {
    const interval = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "ping" }));
      }
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  // ── Send message ───────────────────────────────────────────────────────────
  const sendMessage = () => {
    const text = input.trim();
    if (!text || wsStatus !== "connected" || convStatus !== "active") return;
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return;

    wsRef.current.send(JSON.stringify({ type: "message", content: text }));
    setInput("");
    inputRef.current?.focus();
  };

  // ── Typing indicator ───────────────────────────────────────────────────────
  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInput(e.target.value);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "typing", is_typing: e.target.value.length > 0 }));
    }
  };

  // ── Start new conversation ─────────────────────────────────────────────────
  const startNewConversation = () => {
    clearPersistedConvId(slug);
    setMessages([]);
    setConvId(null);
    setConvStatus("active");
    setIsThinking(false);
    setTypingFrom(null);
    wsRef.current?.close();
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  const isConnected = wsStatus === "connected";

  return (
    <>
      <style>{`
        @keyframes bounce {
          0%, 80%, 100% { transform: translateY(0); opacity: 0.6; }
          40% { transform: translateY(-4px); opacity: 1; }
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Inter', system-ui, sans-serif; }
      `}</style>

      <div style={{
        display: "flex", flexDirection: "column",
        height: "100dvh", width: "100%",
        background: "#ffffff", overflow: "hidden",
      }}>
        {/* ── Header ──────────────────────────────────────────────────────── */}
        <header style={{
          background: "#16a34a", padding: "14px 20px",
          display: "flex", alignItems: "center", justifyContent: "space-between",
          flexShrink: 0,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{
              width: 36, height: 36, borderRadius: "50%",
              background: "rgba(255,255,255,0.2)",
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 16,
            }}>💬</div>
            <div>
              <p style={{ color: "white", fontWeight: 700, fontSize: 15 }}>Support Chat</p>
              <p style={{ color: "rgba(255,255,255,0.75)", fontSize: 11 }}>
                {!isConnected ? "Connecting…" : staffOnline ? "Agent online" : "AI Assistant"}
              </p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            {/* Connection status dot */}
            <div style={{
              width: 8, height: 8, borderRadius: "50%",
              background: isConnected ? "#4ade80" : wsStatus === "error" ? "#f87171" : "#fbbf24",
            }} />
          </div>
        </header>

        {/* ── Messages area ───────────────────────────────────────────────── */}
        <div style={{
          flex: 1, overflowY: "auto", padding: "16px 16px 8px",
          display: "flex", flexDirection: "column",
        }}>
          {/* Welcome message */}
          {messages.length === 0 && isConnected && (
            <div style={{
              textAlign: "center", padding: "40px 20px",
              color: "#94a3b8", fontSize: 13,
            }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>👋</div>
              <p style={{ fontWeight: 600, color: "#475569", marginBottom: 4 }}>
                Welcome! How can we help?
              </p>
              <p style={{ fontSize: 12 }}>
                Our AI assistant is ready to answer your questions.
              </p>
            </div>
          )}

          {/* Connecting state */}
          {!isConnected && messages.length === 0 && (
            <div style={{ textAlign: "center", padding: "40px 20px", color: "#94a3b8" }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>⟳</div>
              <p style={{ fontSize: 13 }}>
                {wsStatus === "error" ? "Connection failed. Retrying…" : "Connecting to support…"}
              </p>
            </div>
          )}

          {/* Message bubbles */}
          {messages.map((msg, idx) => (
            <MessageBubble key={msg.msg_id || idx} msg={msg} />
          ))}

          {/* AI thinking indicator */}
          {isThinking && <ThinkingIndicator />}

          {/* Staff typing indicator */}
          {typingFrom && !isThinking && <TypingIndicator label={typingFrom} />}

          {/* Conversation resolved notice */}
          {convStatus === "resolved" && (
            <div style={{
              textAlign: "center", padding: "16px",
              background: "#f0fdf4", borderRadius: 12, marginTop: 8,
              border: "1px solid #bbf7d0",
            }}>
              <p style={{ fontSize: 13, color: "#166534", fontWeight: 600, marginBottom: 4 }}>
                ✓ Conversation resolved
              </p>
              <p style={{ fontSize: 12, color: "#4ade80", marginBottom: 12 }}>
                Your issue has been resolved. Was this helpful?
              </p>
              <button
                onClick={startNewConversation}
                style={{
                  padding: "8px 16px", borderRadius: 8, border: "none",
                  background: "#16a34a", color: "white",
                  fontSize: 12, fontWeight: 600, cursor: "pointer",
                }}
              >
                Start New Chat
              </button>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* ── Input area ──────────────────────────────────────────────────── */}
        <div style={{
          flexShrink: 0, padding: "12px 16px",
          borderTop: "1px solid #e2e8f0",
          background: "white",
        }}>
          {convStatus === "active" ? (
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
              <textarea
                ref={inputRef}
                rows={1}
                value={input}
                onChange={handleInputChange}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendMessage();
                  }
                }}
                placeholder={isConnected ? "Type a message…" : "Reconnecting…"}
                disabled={!isConnected}
                style={{
                  flex: 1, padding: "10px 14px",
                  borderRadius: 12, border: "1.5px solid #e2e8f0",
                  resize: "none", fontFamily: "inherit", fontSize: 13,
                  outline: "none", lineHeight: 1.5,
                  background: isConnected ? "white" : "#f8fafc",
                  color: "#1e293b",
                  maxHeight: 100, overflowY: "auto",
                  transition: "border-color 0.15s",
                }}
                onFocus={(e) => { e.target.style.borderColor = "#16a34a"; }}
                onBlur={(e) => { e.target.style.borderColor = "#e2e8f0"; }}
              />
              <button
                onClick={sendMessage}
                disabled={!input.trim() || !isConnected}
                style={{
                  width: 40, height: 40, borderRadius: 12, border: "none",
                  background: (!input.trim() || !isConnected) ? "#e2e8f0" : "#16a34a",
                  color: (!input.trim() || !isConnected) ? "#94a3b8" : "white",
                  cursor: (!input.trim() || !isConnected) ? "default" : "pointer",
                  display: "flex", alignItems: "center", justifyContent: "center",
                  fontSize: 18, flexShrink: 0,
                  transition: "background 0.15s",
                }}
              >
                ↑
              </button>
            </div>
          ) : (
            <p style={{ textAlign: "center", fontSize: 12, color: "#94a3b8", padding: "8px 0" }}>
              This conversation is resolved.{" "}
              <button
                onClick={startNewConversation}
                style={{ background: "none", border: "none", color: "#16a34a", cursor: "pointer", fontWeight: 600, fontSize: 12 }}
              >
                Start a new one
              </button>
            </p>
          )}
          <p style={{ textAlign: "center", fontSize: 10, color: "#cbd5e1", marginTop: 6 }}>
            Powered by ResolveAI
          </p>
        </div>
      </div>
    </>
  );
}
