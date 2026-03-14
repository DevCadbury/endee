"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   /dashboard/test — Live Widget Test Page
   Sends real messages to POST /api/v1/chat/incoming using the company API key.
   Shows AI responses with action badges, sources, and a raw JSON debug panel.
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuth() {
  if (typeof window === "undefined") return { token: "", companyId: "", email: "" };
  return {
    token: localStorage.getItem("token") || "",
    companyId: localStorage.getItem("company_id") || "",
    email: localStorage.getItem("email") || "",
  };
}

async function apiFetch(path: string, opts: RequestInit = {}) {
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
  return res.json();
}

/* ---------- Types ---------- */
type Message = {
  role: "user" | "ai";
  text: string;
  action?: string;
  sources?: string[];
  suggested_docs?: string[];
  debug?: any;
  loading?: boolean;
};

const ACTION_STYLES: Record<string, { bg: string; color: string; label: string; dot: string }> = {
  auto_reply: { bg: "#dcfce7", color: "#166534", label: "Auto Resolved", dot: "#22c55e" },
  clarify:    { bg: "#fef3c7", color: "#92400e", label: "Clarifying",    dot: "#f59e0b" },
  escalate:   { bg: "#fee2e2", color: "#991b1b", label: "Escalated",     dot: "#ef4444" },
  error:      { bg: "#fce7f3", color: "#9d174d", label: "Error",         dot: "#ec4899" },
};

const SUGGESTED_PROMPTS = [
  "How do I reset my password?",
  "I need help with my invoice",
  "My account is locked",
  "How do I cancel my subscription?",
  "I didn't receive my order",
];

/* ============================================================================= */
export default function TestPage() {
  const router = useRouter();
  const [apiKey, setApiKey] = useState("");
  const [keyStatus, setKeyStatus] = useState<"loading" | "ready" | "error">("loading");
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [showDebug, setShowDebug] = useState(false);
  const [selectedDebug, setSelectedDebug] = useState<any>(null);
  const [sessionId] = useState(() => `test-${Date.now()}`);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { email } = getAuth();

  /* ---- Auth + API key setup ---- */
  useEffect(() => {
    if (!getAuth().token) { router.push("/login"); return; }
    const stored = localStorage.getItem("api_key");
    if (stored) { setApiKey(stored); setKeyStatus("ready"); return; }
    apiFetch("/api/v1/auth/api-key", { method: "POST" })
      .then((d) => {
        setApiKey(d.api_key);
        localStorage.setItem("api_key", d.api_key);
        setKeyStatus("ready");
      })
      .catch(() => setKeyStatus("error"));
  }, [router]);

  /* ---- Auto-scroll ---- */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ---- Send message ---- */
  const sendMessage = async (text?: string) => {
    const msg = (text || input).trim();
    if (!msg || !apiKey || sending) return;
    setInput("");
    setSending(true);

    setMessages((prev) => [
      ...prev,
      { role: "user", text: msg },
      { role: "ai", text: "", loading: true },
    ]);

    try {
      const res = await fetch(`${API_URL}/api/v1/chat/incoming`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-API-Key": apiKey },
        body: JSON.stringify({ customer_message: msg, customer_id: sessionId }),
      });
      const data = await res.json();

      setMessages((prev) => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = {
          role: "ai",
          text: data.message || data.detail || "No response received.",
          action: data.action,
          sources: data.sources,
          suggested_docs: data.suggested_docs,
          debug: data,
        };
        return msgs;
      });
    } catch (err) {
      setMessages((prev) => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = {
          role: "ai",
          text: "Network error — could not reach the AI service.",
          action: "error",
        };
        return msgs;
      });
    }

    setSending(false);
    inputRef.current?.focus();
  };

  const resetChat = () => {
    setMessages([]);
    setSelectedDebug(null);
    inputRef.current?.focus();
  };

  /* ---- Render ---- */
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--slate-50)" }}>
      {/* ---- Sidebar ---- */}
      <aside style={{
        width: 240, flexShrink: 0,
        background: "white", borderRight: "1px solid var(--slate-200)",
        padding: "20px 0", display: "flex", flexDirection: "column",
      }}>
        <div style={{ padding: "0 20px 24px", display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: "var(--primary)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 800, fontSize: 15,
          }}>R</div>
          <span style={{ fontWeight: 700, fontSize: 17, color: "var(--slate-900)" }}>ResolveAI</span>
        </div>

        <nav style={{ flex: 1 }}>
          {[
            { href: "/dashboard", label: "Dashboard", icon: "📊", active: false },
            { href: "/dashboard/test", label: "Test Widget", icon: "🧪", active: true },
            { href: "/admin", label: "Admin Panel", icon: "🛡️", active: false },
          ].map((item) => (
            <a key={item.href} href={item.href} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "10px 20px", textDecoration: "none",
              background: item.active ? "var(--primary-50)" : "transparent",
              color: item.active ? "var(--primary-dark)" : "var(--slate-600)",
              fontWeight: item.active ? 600 : 400,
              fontSize: 14,
              borderLeft: item.active ? "3px solid var(--primary)" : "3px solid transparent",
              transition: "all 0.15s ease",
            }}>
              <span style={{ fontSize: 16 }}>{item.icon}</span>
              {item.label}
            </a>
          ))}
        </nav>

        <div style={{ padding: "16px 20px", borderTop: "1px solid var(--slate-100)" }}>
          <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 4 }}>{email}</p>
          <button
            onClick={() => { localStorage.clear(); router.push("/login"); }}
            style={{ background: "none", border: "none", color: "var(--slate-500)", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}
          >Sign Out</button>
        </div>
      </aside>

      {/* ---- Main ---- */}
      <main style={{ flex: 1, padding: 32, display: "flex", flexDirection: "column", minWidth: 0 }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 24 }}>
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Live Widget Test</h1>
            <p style={{ fontSize: 14, color: "var(--slate-500)" }}>
              Send real customer messages and see the AI decision, confidence, and KB sources in real time.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              onClick={resetChat}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1px solid var(--slate-200)",
                background: "white", color: "var(--slate-700)", fontSize: 13,
                cursor: "pointer", fontFamily: "inherit",
              }}
            >Clear Chat</button>
            <button
              onClick={() => setShowDebug(!showDebug)}
              style={{
                padding: "8px 16px", borderRadius: 8, border: "1px solid var(--slate-200)",
                background: showDebug ? "var(--slate-900)" : "white",
                color: showDebug ? "white" : "var(--slate-700)",
                fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              }}
            >{showDebug ? "Hide Debug" : "Show Debug"}</button>
          </div>
        </div>

        {/* API key status bar */}
        {keyStatus === "loading" && (
          <div style={{ padding: "10px 16px", background: "#fef3c7", borderRadius: 8, marginBottom: 16, fontSize: 13, color: "#92400e" }}>
            Generating API key...
          </div>
        )}
        {keyStatus === "error" && (
          <div style={{ padding: "10px 16px", background: "#fee2e2", borderRadius: 8, marginBottom: 16, fontSize: 13, color: "#991b1b" }}>
            Failed to generate API key. <a href="/dashboard" style={{ color: "#991b1b" }}>Go to Dashboard → Developer</a> to generate one manually.
          </div>
        )}
        {keyStatus === "ready" && (
          <div style={{ marginBottom: 16, display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#22c55e" }} />
            <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
              API Key:{" "}
              <code style={{ fontFamily: "monospace", background: "var(--slate-100)", padding: "2px 6px", borderRadius: 4 }}>
                {apiKey.slice(0, 24)}…
              </code>
            </span>
          </div>
        )}

        {/* Split layout */}
        <div style={{ display: "flex", gap: 16, flex: 1, minHeight: 0 }}>
          {/* ---- Chat Panel ---- */}
          <div style={{
            flex: 1, display: "flex", flexDirection: "column",
            background: "white", borderRadius: 12, border: "1px solid var(--slate-200)",
            overflow: "hidden", minWidth: 0,
          }}>
            {/* Chat header */}
            <div style={{
              padding: "14px 20px", background: "var(--primary)", color: "white",
              display: "flex", alignItems: "center", gap: 12,
            }}>
              <div style={{
                width: 36, height: 36, borderRadius: "50%", background: "rgba(255,255,255,0.2)",
                display: "flex", alignItems: "center", justifyContent: "center", fontSize: 18,
              }}>🤖</div>
              <div>
                <p style={{ fontWeight: 600, fontSize: 15, margin: 0 }}>AI Support Agent</p>
                <p style={{ fontSize: 12, opacity: 0.8, margin: 0 }}>Powered by ResolveAI</p>
              </div>
              <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6 }}>
                <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#4ade80" }} />
                <span style={{ fontSize: 12, opacity: 0.9 }}>Online</span>
              </div>
            </div>

            {/* Messages */}
            <div style={{
              flex: 1, overflowY: "auto", padding: 16,
              display: "flex", flexDirection: "column", gap: 12,
              minHeight: 400,
            }}>
              {messages.length === 0 && (
                <div style={{ textAlign: "center", padding: "40px 20px", color: "var(--slate-400)" }}>
                  <p style={{ fontSize: 40, marginBottom: 12 }}>💬</p>
                  <p style={{ fontSize: 16, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>
                    Test your AI widget
                  </p>
                  <p style={{ fontSize: 13, marginBottom: 24 }}>
                    Type any customer question below to see how your AI responds.
                  </p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, justifyContent: "center" }}>
                    {SUGGESTED_PROMPTS.map((q) => (
                      <button key={q} onClick={() => sendMessage(q)} style={{
                        padding: "7px 14px", borderRadius: 20,
                        border: "1px solid var(--slate-200)",
                        background: "var(--slate-50)", fontSize: 13,
                        cursor: "pointer", fontFamily: "inherit",
                        color: "var(--slate-600)",
                        transition: "background 0.15s",
                      }}>
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {messages.map((msg, i) => (
                <div key={i} style={{
                  display: "flex",
                  justifyContent: msg.role === "user" ? "flex-end" : "flex-start",
                }}>
                  <div style={{ maxWidth: "78%" }}>
                    {msg.loading ? (
                      <div style={{
                        padding: "12px 18px",
                        background: "var(--slate-100)", borderRadius: "18px 18px 18px 4px",
                        display: "flex", gap: 5, alignItems: "center",
                      }}>
                        {[0, 1, 2].map((j) => (
                          <div key={j} style={{
                            width: 8, height: 8, borderRadius: "50%",
                            background: "var(--slate-400)",
                            animation: `blink 1.4s ease-in-out ${j * 0.2}s infinite`,
                          }} />
                        ))}
                        <style>{`@keyframes blink { 0%,80%,100%{opacity:.2} 40%{opacity:1} }`}</style>
                      </div>
                    ) : (
                      <>
                        <div style={{
                          padding: "12px 16px",
                          background: msg.role === "user" ? "var(--primary)" : "var(--slate-100)",
                          color: msg.role === "user" ? "white" : "var(--slate-800)",
                          borderRadius: msg.role === "user"
                            ? "18px 18px 4px 18px"
                            : "18px 18px 18px 4px",
                          fontSize: 14, lineHeight: 1.6,
                          boxShadow: "0 1px 2px rgba(0,0,0,0.05)",
                        }}>
                          {msg.text}
                        </div>

                        {/* Action metadata row */}
                        {msg.action && (
                          <div style={{ marginTop: 6, display: "flex", gap: 6, flexWrap: "wrap", alignItems: "center" }}>
                            <span style={{
                              fontSize: 11, padding: "3px 9px", borderRadius: 4, fontWeight: 600,
                              background: ACTION_STYLES[msg.action]?.bg || "#e2e8f0",
                              color: ACTION_STYLES[msg.action]?.color || "var(--slate-600)",
                              display: "flex", alignItems: "center", gap: 4,
                            }}>
                              <span style={{
                                width: 6, height: 6, borderRadius: "50%",
                                background: ACTION_STYLES[msg.action]?.dot || "#94a3b8",
                                display: "inline-block",
                              }} />
                              {ACTION_STYLES[msg.action]?.label || msg.action}
                            </span>

                            {msg.sources && msg.sources.length > 0 && (
                              <span style={{
                                fontSize: 11, padding: "3px 9px", borderRadius: 4,
                                background: "#eff6ff", color: "#1e40af",
                                fontWeight: 500,
                              }}>
                                📄 {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                              </span>
                            )}

                            {msg.debug && (
                              <button
                                onClick={() => {
                                  setSelectedDebug(msg.debug);
                                  setShowDebug(true);
                                }}
                                style={{
                                  fontSize: 11, padding: "3px 9px", borderRadius: 4,
                                  border: "1px solid var(--slate-200)", background: "white",
                                  cursor: "pointer", color: "var(--slate-500)", fontFamily: "inherit",
                                  fontWeight: 500,
                                }}
                              >⚙ Debug</button>
                            )}
                          </div>
                        )}

                        {/* Sources list */}
                        {msg.sources && msg.sources.length > 0 && (
                          <div style={{ marginTop: 6, paddingLeft: 4 }}>
                            {msg.sources.map((src, si) => (
                              <p key={si} style={{ fontSize: 11, color: "var(--slate-400)", margin: "1px 0" }}>
                                └ {src}
                              </p>
                            ))}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>

            {/* Input area */}
            <div style={{ padding: 16, borderTop: "1px solid var(--slate-100)", display: "flex", gap: 8 }}>
              <input
                ref={inputRef}
                className="input"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
                }}
                placeholder="Type a customer message and press Enter…"
                disabled={keyStatus !== "ready" || sending}
                style={{ flex: 1 }}
                autoFocus
              />
              <button
                className="btn btn-primary"
                onClick={() => sendMessage()}
                disabled={keyStatus !== "ready" || sending || !input.trim()}
                style={{ flexShrink: 0, minWidth: 72 }}
              >
                {sending ? "…" : "Send"}
              </button>
            </div>
          </div>

          {/* ---- Debug Panel ---- */}
          {showDebug && (
            <div style={{
              width: 380, flexShrink: 0,
              background: "var(--slate-900)", borderRadius: 12,
              border: "1px solid #334155",
              display: "flex", flexDirection: "column", overflow: "hidden",
            }}>
              <div style={{
                padding: "14px 20px", borderBottom: "1px solid #334155",
                display: "flex", justifyContent: "space-between", alignItems: "center",
              }}>
                <p style={{ color: "#94a3b8", fontSize: 13, fontWeight: 600, margin: 0 }}>
                  API Response Debug
                </p>
                <button
                  onClick={() => setSelectedDebug(null)}
                  style={{ background: "none", border: "none", color: "#475569", fontSize: 16, cursor: "pointer" }}
                >×</button>
              </div>

              <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
                {selectedDebug ? (
                  <>
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                      {["action", "context_passed_to_agent"].map((key) => (
                        selectedDebug[key] !== undefined && (
                          <span key={key} style={{
                            fontSize: 11, padding: "3px 8px", borderRadius: 4,
                            background: "#1e293b", color: "#94a3b8",
                          }}>
                            {key}: <strong style={{ color: "#a5f3fc" }}>{String(selectedDebug[key])}</strong>
                          </span>
                        )
                      ))}
                    </div>

                    {selectedDebug.sources?.length > 0 && (
                      <div style={{ marginBottom: 12 }}>
                        <p style={{ fontSize: 11, color: "#475569", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>Sources</p>
                        {selectedDebug.sources.map((src: string, i: number) => (
                          <p key={i} style={{ fontSize: 12, color: "#7dd3fc", margin: "2px 0" }}>• {src}</p>
                        ))}
                      </div>
                    )}

                    <p style={{ fontSize: 11, color: "#475569", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: 8 }}>Full Response</p>
                    <pre style={{
                      color: "#a5f3fc", fontSize: 12, margin: 0,
                      whiteSpace: "pre-wrap", wordBreak: "break-all",
                      fontFamily: "monospace",
                    }}>
                      {JSON.stringify(selectedDebug, null, 2)}
                    </pre>
                  </>
                ) : (
                  <div style={{ textAlign: "center", paddingTop: 40 }}>
                    <p style={{ fontSize: 24, marginBottom: 12 }}>🔍</p>
                    <p style={{ color: "#475569", fontSize: 13 }}>
                      Click the <strong style={{ color: "#94a3b8" }}>⚙ Debug</strong> button on any AI message to inspect the full API response.
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
