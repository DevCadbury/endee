"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   Dashboard — Company overview, KB, API keys, tickets, and audit.
   Sidebar navigation with overview stats, knowledge base management,
   developer tools, inbox for escalated tickets, and audit trail.
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ---------- Auth helpers ---------- */
function getAuth() {
  if (typeof window === "undefined") return { token: "", companyId: "", email: "", role: "" };
  return {
    token: localStorage.getItem("token") || "",
    companyId: localStorage.getItem("company_id") || "",
    email: localStorage.getItem("email") || "",
    role: localStorage.getItem("role") || "admin",
  };
}

async function apiFetch(path: string, opts: RequestInit = {}) {
  const { token } = getAuth();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(opts.headers as Record<string, string> || {}),
  };
  if (!(opts.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const res = await fetch(`${API_URL}${path}`, { ...opts, headers });
  if (res.status === 401) {
    localStorage.clear();
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.detail || `Request failed (${res.status})`);
  }
  return data;
}

/* ---------- Tab type ---------- */
type Tab = "overview" | "kb" | "developer" | "inbox" | "audit";

/* ============================================================================= */
export default function DashboardPage() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("overview");
  const [email, setEmail] = useState("");
  useEffect(() => {
    const auth = getAuth();
    setEmail(auth.email);
    if (!auth.token) { router.push("/login"); return; }
    if (auth.role === "staff") { router.push("/staff"); return; }
    if (auth.role === "superadmin") { router.push("/superadmin"); return; }
  }, [router]);

  const tabs: { key: Tab; label: string; icon: string }[] = [
    { key: "overview", label: "Overview", icon: "📊" },
    { key: "kb", label: "Knowledge Base", icon: "📚" },
    { key: "developer", label: "Developer", icon: "⚡" },
    { key: "inbox", label: "Inbox", icon: "📬" },
    { key: "audit", label: "Audit Log", icon: "📋" },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--slate-50)" }}>
      {/* ---- Sidebar ---- */}
      <aside
        style={{
          width: 240,
          background: "var(--white)",
          borderRight: "1px solid var(--slate-200)",
          padding: "20px 0",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <div style={{ padding: "0 20px 24px", display: "flex", alignItems: "center", gap: 10 }}>
          <div
            style={{
              width: 32, height: 32, borderRadius: 8, background: "var(--primary)",
              display: "flex", alignItems: "center", justifyContent: "center",
              color: "white", fontWeight: 800, fontSize: 15,
            }}
          >R</div>
          <span style={{ fontWeight: 700, fontSize: 17, color: "var(--slate-900)" }}>ResolveAI</span>
        </div>

        <nav style={{ flex: 1 }}>
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              style={{
                display: "flex", alignItems: "center", gap: 10,
                width: "100%", padding: "10px 20px", border: "none",
                background: tab === t.key ? "var(--primary-50)" : "transparent",
                color: tab === t.key ? "var(--primary-dark)" : "var(--slate-600)",
                fontWeight: tab === t.key ? 600 : 400,
                fontSize: 14, cursor: "pointer",
                borderLeft: tab === t.key ? "3px solid var(--primary)" : "3px solid transparent",
                transition: "all 0.15s ease",
                fontFamily: "inherit",
              }}
            >
              <span style={{ fontSize: 16 }}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        {/* External page links */}
        <div style={{ padding: "8px 0", borderTop: "1px solid var(--slate-100)" }}>
          {[
            { href: "/dashboard/test", label: "Test Widget", icon: "🧪" },
            { href: "/admin", label: "Admin Panel", icon: "🛡️" },
            { href: "/staff", label: "Staff Inbox", icon: "💬" },
          ].map((item) => (
            <a key={item.href} href={item.href} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "9px 20px", textDecoration: "none",
              color: "var(--slate-500)", fontSize: 13,
              borderLeft: "3px solid transparent",
              transition: "color 0.15s",
            }}>
              <span style={{ fontSize: 15 }}>{item.icon}</span>
              {item.label}
            </a>
          ))}
        </div>

        <div style={{ padding: "12px 20px", borderTop: "1px solid var(--slate-100)" }}>
          <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 4 }}>{email}</p>
          <button
            onClick={() => { localStorage.clear(); router.push("/login"); }}
            style={{
              background: "none", border: "none", color: "var(--slate-500)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit",
            }}
          >
            Sign Out
          </button>
        </div>
      </aside>

      {/* ---- Main Content ---- */}
      <main style={{ flex: 1, padding: 32, overflowY: "auto" }}>
        {tab === "overview" && <OverviewTab />}
        {tab === "kb" && <KBTab />}
        {tab === "developer" && <DeveloperTab />}
        {tab === "inbox" && <InboxTab />}
        {tab === "audit" && <AuditTab />}
      </main>
    </div>
  );
}

/* ---------- Overview Tab ---------- */
function OverviewTab() {
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    apiFetch("/api/v1/dashboard/stats").then(setStats).catch(console.error);
  }, []);

  const cards = stats
    ? [
        { label: "Total Chats", value: stats.total_chats, color: "var(--slate-700)" },
        { label: "Auto-Resolved", value: `${stats.auto_resolve_rate}%`, color: "var(--success)" },
        { label: "Escalated", value: `${stats.escalation_rate}%`, color: "var(--danger)" },
        { label: "Pending Tickets", value: stats.pending_tickets, color: "var(--warning)" },
        { label: "KB Documents", value: stats.total_documents, color: "var(--info)" },
        { label: "Clarified", value: stats.clarified, color: "var(--slate-500)" },
      ]
    : [];

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24, fontWeight: 700 }}>Dashboard</h1>
      {!stats ? (
        <p style={{ color: "var(--slate-400)" }}>Loading stats...</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 16 }}>
          {cards.map((c, i) => (
            <div key={i} className="card" style={{ textAlign: "center" }}>
              <p style={{ fontSize: 13, color: "var(--slate-500)", marginBottom: 4 }}>{c.label}</p>
              <p style={{ fontSize: 28, fontWeight: 700, color: c.color }}>{c.value}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Knowledge Base Tab ---------- */
function KBTab() {
  const [docs, setDocs] = useState<any[]>([]);
  const [form, setForm] = useState({ title: "", content: "", source_type: "text", category: "general" });
  const [uploading, setUploading] = useState(false);

  const loadDocs = () => apiFetch("/api/v1/kb/documents").then((d) => setDocs(d.documents || []));
  useEffect(() => { loadDocs(); }, []);

  const handleIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploading(true);
    try {
      await apiFetch("/api/v1/kb/ingest", { method: "POST", body: JSON.stringify(form) });
      setForm({ title: "", content: "", source_type: "text", category: "general" });
      loadDocs();
    } catch (err) { console.error(err); }
    setUploading(false);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24, fontWeight: 700 }}>Knowledge Base</h1>

      {/* Upload form */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 16, marginBottom: 16, fontWeight: 600 }}>Ingest Document</h3>
        <form onSubmit={handleIngest} style={{ display: "grid", gap: 12 }}>
          <input className="input" placeholder="Document title" value={form.title}
            onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))} required />
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
            <select className="input" value={form.source_type}
              onChange={(e) => setForm((p) => ({ ...p, source_type: e.target.value }))}>
              <option value="text">Text</option><option value="slack">Slack</option>
              <option value="email">Email</option><option value="confluence">Confluence</option>
              <option value="notion">Notion</option><option value="drive">Drive</option>
            </select>
            <select className="input" value={form.category}
              onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}>
              <option value="general">General</option><option value="billing">Billing</option>
              <option value="technical">Technical</option><option value="account">Account</option>
            </select>
          </div>
          <textarea className="input" rows={6} placeholder="Paste document content..." value={form.content}
            onChange={(e) => setForm((p) => ({ ...p, content: e.target.value }))} required
            style={{ resize: "vertical", fontFamily: "inherit" }} />
          <button className="btn btn-primary" type="submit" disabled={uploading} style={{ justifySelf: "start" }}>
            {uploading ? "Ingesting..." : "Ingest Document"}
          </button>
        </form>
      </div>

      {/* Document list */}
      <div className="card">
        <h3 style={{ fontSize: 16, marginBottom: 16, fontWeight: 600 }}>
          Ingested Documents ({docs.length})
        </h3>
        {docs.length === 0 ? (
          <p style={{ color: "var(--slate-400)", fontSize: 14 }}>No documents yet. Upload one above.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {docs.map((doc: any) => (
              <div key={doc._id} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px", background: "var(--slate-50)", borderRadius: 8,
              }}>
                <div>
                  <p style={{ fontWeight: 500, fontSize: 14 }}>{doc.title}</p>
                  <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
                    {doc.source_type} · {doc.chunk_count} chunks
                  </p>
                </div>
                <span style={{
                  fontSize: 11, padding: "3px 8px", borderRadius: 4,
                  background: "var(--primary-100)", color: "var(--primary-dark)", fontWeight: 500,
                }}>{doc.source_type}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------- Developer Tab ---------- */
function DeveloperTab() {
  const [keys, setKeys] = useState<any[]>([]);
  const [newKey, setNewKey] = useState("");
  const [generating, setGenerating] = useState(false);
  const [loading, setLoading] = useState(true);
  const [copied, setCopied] = useState("");
  const slug = typeof window !== "undefined" ? localStorage.getItem("slug") || "" : "";

  const loadKeys = () => {
    setLoading(true);
    apiFetch("/api/v1/auth/api-keys")
      .then((d) => setKeys(d.api_keys || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadKeys(); }, []);

  const generateKey = async () => {
    setGenerating(true);
    try {
      const data = await apiFetch("/api/v1/auth/api-key", { method: "POST" });
      setNewKey(data.api_key);
      loadKeys();
    } catch (err) { console.error(err); }
    setGenerating(false);
  };

  const deleteKey = async (keyId: string) => {
    if (!confirm("Revoke this API key? Any widgets using it will stop working.")) return;
    try {
      await apiFetch(`/api/v1/auth/api-key/${keyId}`, { method: "DELETE" });
      loadKeys();
    } catch (err) { console.error(err); }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text).then(() => { setCopied(id); setTimeout(() => setCopied(""), 2000); });
  };

  const widgetSnippet = `<script src="https://your-domain.com/widget.js"\n  data-slug="${slug}"\n  data-api-url="http://localhost:8000"></script>`;

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24, fontWeight: 700 }}>Developer</h1>

      {/* API Keys */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16 }}>
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>API Keys</h3>
            <p style={{ fontSize: 13, color: "var(--slate-500)" }}>
              Manage API keys for your chat widget integration.
            </p>
          </div>
          <button className="btn btn-primary" onClick={generateKey} disabled={generating} style={{ fontSize: 13, flexShrink: 0 }}>
            {generating ? "Generating..." : "+ New Key"}
          </button>
        </div>

        {/* Newly generated key banner */}
        {newKey && (
          <div style={{
            padding: "12px 16px", background: "#dcfce7", borderRadius: 8,
            border: "1px solid #86efac", marginBottom: 16,
          }}>
            <p style={{ fontSize: 12, color: "#166534", fontWeight: 600, marginBottom: 6 }}>
              New API key generated — copy it now, it won't be shown again in full!
            </p>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <code style={{
                flex: 1, padding: "8px 12px", background: "white", borderRadius: 6,
                fontSize: 12, fontFamily: "monospace", wordBreak: "break-all",
                border: "1px solid #bbf7d0",
              }}>{newKey}</code>
              <button
                onClick={() => copyToClipboard(newKey, "new")}
                style={{
                  padding: "6px 12px", borderRadius: 6, border: "1px solid #86efac",
                  background: copied === "new" ? "#166534" : "white",
                  color: copied === "new" ? "white" : "#166534",
                  fontSize: 12, cursor: "pointer", fontFamily: "inherit", fontWeight: 500,
                  flexShrink: 0,
                }}
              >{copied === "new" ? "Copied!" : "Copy"}</button>
            </div>
          </div>
        )}

        {/* Keys table */}
        {loading ? (
          <p style={{ color: "var(--slate-400)", fontSize: 14 }}>Loading keys...</p>
        ) : keys.length === 0 ? (
          <p style={{ color: "var(--slate-400)", fontSize: 14, textAlign: "center", padding: 24 }}>
            No API keys yet. Click &quot;+ New Key&quot; to generate one.
          </p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {keys.map((k: any) => (
              <div key={k._id} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px", background: "var(--slate-50)", borderRadius: 8,
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <code style={{ fontSize: 13, fontFamily: "monospace", color: "var(--slate-700)" }}>
                    {k.key_masked || k.key}
                  </code>
                  <p style={{ fontSize: 11, color: "var(--slate-400)", marginTop: 4 }}>
                    Created: {new Date(k.created_at).toLocaleDateString()}
                    {k.active === false && <span style={{ color: "#ef4444", marginLeft: 8 }}>(Inactive)</span>}
                  </p>
                </div>
                <button
                  onClick={() => deleteKey(k._id)}
                  style={{
                    padding: "5px 12px", borderRadius: 6, border: "1px solid #fecaca",
                    background: "white", color: "#dc2626", fontSize: 12,
                    cursor: "pointer", fontFamily: "inherit", fontWeight: 500,
                    flexShrink: 0,
                  }}
                >Revoke</button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Widget Integration */}
      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 16, marginBottom: 12, fontWeight: 600 }}>Widget Integration</h3>
        <p style={{ fontSize: 14, color: "var(--slate-500)", marginBottom: 16 }}>
          Add this script tag to your website to embed the live chat widget.
        </p>
        <div style={{
          padding: "14px 18px", background: "var(--slate-900)", borderRadius: 8,
          fontFamily: "monospace", fontSize: 13, color: "#a5f3fc", overflowX: "auto",
          position: "relative",
        }}>
          <pre style={{ margin: 0 }}>{widgetSnippet}</pre>
          <button
            onClick={() => copyToClipboard(widgetSnippet, "snippet")}
            style={{
              position: "absolute", top: 8, right: 8,
              padding: "4px 10px", borderRadius: 4,
              background: copied === "snippet" ? "#22c55e" : "#334155",
              color: "white", fontSize: 11, cursor: "pointer",
              border: "none", fontFamily: "inherit",
            }}
          >{copied === "snippet" ? "Copied!" : "Copy"}</button>
        </div>
      </div>

      {/* Company Slug */}
      <div className="card">
        <h3 style={{ fontSize: 16, marginBottom: 12, fontWeight: 600 }}>Company Info</h3>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div>
            <p style={{ fontSize: 12, color: "var(--slate-500)", marginBottom: 4 }}>Company Slug</p>
            <code style={{
              display: "block", padding: "8px 12px", background: "var(--slate-50)",
              borderRadius: 6, fontSize: 13, fontFamily: "monospace",
            }}>{slug || "—"}</code>
          </div>
          <div>
            <p style={{ fontSize: 12, color: "var(--slate-500)", marginBottom: 4 }}>Login URL</p>
            <code style={{
              display: "block", padding: "8px 12px", background: "var(--slate-50)",
              borderRadius: 6, fontSize: 13, fontFamily: "monospace",
            }}>/login/{slug}</code>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ---------- Inbox Tab ---------- */
function InboxTab() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [resolutions, setResolutions] = useState<Record<string, string>>({});

  const loadTickets = () => apiFetch("/api/v1/dashboard/tickets?status=pending").then((d) => setTickets(d.tickets || []));
  useEffect(() => { loadTickets(); }, []);

  const resolveTicket = async (id: string) => {
    const resolution = resolutions[id];
    if (!resolution?.trim()) return;
    try {
      await apiFetch(`/api/v1/dashboard/tickets/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ resolution, ingest_to_kb: true }),
      });
      loadTickets();
    } catch (err) { console.error(err); }
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24, fontWeight: 700 }}>
        Inbox — Escalated Tickets ({tickets.length})
      </h1>

      {tickets.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p style={{ fontSize: 18, marginBottom: 4 }}>🎉</p>
          <p style={{ color: "var(--slate-500)", fontSize: 14 }}>No pending tickets. AI is handling everything!</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {tickets.map((t: any) => (
            <div key={t._id} className="card">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "start", marginBottom: 12 }}>
                <div>
                  <span style={{
                    fontSize: 11, padding: "3px 8px", borderRadius: 4,
                    background: "#fef3c7", color: "#92400e", fontWeight: 500,
                  }}>Pending</span>
                </div>
                <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
                  {new Date(t.created_at).toLocaleDateString()}
                </span>
              </div>

              <p style={{ fontWeight: 500, fontSize: 14, marginBottom: 8 }}>Customer Message:</p>
              <p style={{
                background: "var(--slate-50)", padding: "10px 14px", borderRadius: 8,
                fontSize: 13, color: "var(--slate-700)", marginBottom: 12,
              }}>
                {t.customer_message}
              </p>

              {t.ai_context && (
                <>
                  <p style={{ fontWeight: 500, fontSize: 14, marginBottom: 4, color: "var(--slate-500)" }}>AI Context:</p>
                  <p style={{ fontSize: 13, color: "var(--slate-400)", marginBottom: 12 }}>{t.ai_context}</p>
                </>
              )}

              <textarea
                className="input"
                rows={2}
                placeholder="Type your resolution..."
                value={resolutions[t._id] || ""}
                onChange={(e) => setResolutions((p) => ({ ...p, [t._id]: e.target.value }))}
                style={{ marginBottom: 8, fontSize: 13, fontFamily: "inherit", resize: "vertical" }}
              />
              <button className="btn btn-primary" onClick={() => resolveTicket(t._id)} style={{ fontSize: 13 }}>
                Resolve & Learn
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- Audit Log Tab ---------- */
function AuditTab() {
  const [logs, setLogs] = useState<any[]>([]);
  useEffect(() => {
    apiFetch("/api/v1/dashboard/audit").then((d) => setLogs(d.audit_logs || [])).catch(console.error);
  }, []);

  const eventColors: Record<string, string> = {
    rag_generation: "var(--success)",
    escalation: "var(--danger)",
    clarification: "var(--warning)",
    intent_classification: "var(--info)",
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, marginBottom: 24, fontWeight: 700 }}>Audit Log</h1>

      {logs.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p style={{ color: "var(--slate-400)", fontSize: 14 }}>No audit logs yet.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {logs.map((log: any, i: number) => (
            <div key={i} className="card" style={{ padding: "14px 20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                <span style={{
                  fontSize: 11, padding: "2px 8px", borderRadius: 4, fontWeight: 500,
                  background: (eventColors[log.event_type] || "var(--slate-400)") + "18",
                  color: eventColors[log.event_type] || "var(--slate-600)",
                }}>
                  {log.event_type}
                </span>
                <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
                  {log.latency_ms}ms · {new Date(log.created_at).toLocaleTimeString()}
                </span>
              </div>
              <p style={{ fontSize: 13, color: "var(--slate-600)" }}>
                <strong>Q:</strong> {log.request_summary?.substring(0, 100)}
              </p>
              <p style={{ fontSize: 13, color: "var(--slate-500)", marginTop: 2 }}>
                <strong>A:</strong> {log.response_summary?.substring(0, 100)}
              </p>
              {log.confidence > 0 && (
                <p style={{ fontSize: 12, color: "var(--slate-400)", marginTop: 4 }}>
                  Confidence: {(log.confidence * 100).toFixed(0)}% · Model: {log.model}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
