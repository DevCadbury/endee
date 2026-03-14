"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   /superadmin — Platform-wide Global View
   Read-only global views: Companies, Users, Conversations, Audit, Stats.
   Only accessible to users with role="superadmin".
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function getAuth() {
  if (typeof window === "undefined") return { token: "", email: "" };
  return {
    token: localStorage.getItem("token") || "",
    email: localStorage.getItem("email") || "",
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
  return res.json();
}

type SuperTab = "stats" | "companies" | "users" | "conversations" | "audit";

/* ============================================================================= */
export default function SuperAdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<SuperTab>("stats");
  const { email } = getAuth();

  useEffect(() => {
    const token = localStorage.getItem("token");
    const role = localStorage.getItem("role");
    if (!token) { router.push("/login"); return; }
    if (role !== "superadmin") { router.push("/dashboard"); return; }
  }, [router]);

  const tabs: { key: SuperTab; label: string; icon: string }[] = [
    { key: "stats",         label: "Global Stats",   icon: "📊" },
    { key: "companies",     label: "Companies",       icon: "🏢" },
    { key: "users",         label: "Users",           icon: "👥" },
    { key: "conversations", label: "Conversations",   icon: "💬" },
    { key: "audit",         label: "Audit Logs",      icon: "📋" },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#0f172a" }}>
      {/* ---- Dark Sidebar ---- */}
      <aside style={{
        width: 240, flexShrink: 0,
        background: "#0f172a", borderRight: "1px solid #1e293b",
        padding: "20px 0", display: "flex", flexDirection: "column",
      }}>
        <div style={{ padding: "0 20px 20px", display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: "#7c3aed",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 800, fontSize: 15,
          }}>R</div>
          <div>
            <p style={{ fontWeight: 700, fontSize: 16, color: "white", margin: 0 }}>ResolveAI</p>
            <p style={{ fontSize: 10, color: "#a78bfa", margin: 0, fontWeight: 600, letterSpacing: 1 }}>SUPERADMIN</p>
          </div>
        </div>

        <div style={{ height: 1, background: "#1e293b", margin: "0 20px 16px" }} />

        <nav style={{ flex: 1 }}>
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              display: "flex", alignItems: "center", gap: 10,
              width: "100%", padding: "10px 20px", border: "none",
              background: tab === t.key ? "rgba(167,139,250,0.1)" : "transparent",
              color: tab === t.key ? "#a78bfa" : "#64748b",
              fontWeight: tab === t.key ? 600 : 400,
              fontSize: 14, cursor: "pointer",
              borderLeft: tab === t.key ? "3px solid #a78bfa" : "3px solid transparent",
              fontFamily: "inherit",
              transition: "all 0.15s",
            }}>
              <span style={{ fontSize: 16 }}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        <div style={{ padding: "16px 20px", borderTop: "1px solid #1e293b" }}>
          <p style={{ fontSize: 12, color: "#334155", marginBottom: 6 }}>{email}</p>
          <button
            onClick={() => { localStorage.clear(); router.push("/login"); }}
            style={{ background: "none", border: "none", color: "#475569", fontSize: 13, cursor: "pointer", fontFamily: "inherit" }}
          >Sign Out</button>
        </div>
      </aside>

      {/* ---- Main ---- */}
      <main style={{ flex: 1, background: "#f8fafc", padding: 32, overflowY: "auto", minWidth: 0 }}>
        {tab === "stats"         && <GlobalStatsTab />}
        {tab === "companies"     && <CompaniesTab />}
        {tab === "users"         && <UsersTab />}
        {tab === "conversations" && <ConversationsTab />}
        {tab === "audit"         && <AuditTab />}
      </main>
    </div>
  );
}

/* ============================================================================= */
/* Stats Tab                                                                       */
/* ============================================================================= */
function GlobalStatsTab() {
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    apiFetch("/api/v1/superadmin/stats").then(setStats).catch(console.error);
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Global Stats</h1>
      <p style={{ fontSize: 14, color: "var(--slate-500)", marginBottom: 28 }}>
        Platform-wide aggregate metrics across all companies.
      </p>

      {!stats ? (
        <p style={{ color: "var(--slate-400)" }}>Loading stats...</p>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 16 }}>
          {[
            { label: "Companies",            value: stats.total_companies,       icon: "🏢", color: "#7c3aed" },
            { label: "Users",                value: stats.total_users,           icon: "👥", color: "#3b82f6" },
            { label: "Total Conversations",  value: stats.total_conversations,   icon: "💬", color: "#0ea5e9" },
            { label: "Active Conversations", value: stats.active_conversations,  icon: "🟢", color: "#22c55e" },
            { label: "Resolved",             value: stats.resolved_conversations,icon: "✅", color: "#6366f1" },
            { label: "KB Entries",           value: stats.total_kb_entries,      icon: "📚", color: "#f59e0b" },
            { label: "Chat Sessions",        value: stats.total_chat_sessions,   icon: "🤖", color: "#8b5cf6" },
            { label: "Auto-Resolve Rate",    value: `${stats.global_auto_resolve_rate}%`, icon: "⚡", color: "#22c55e" },
          ].map((c, i) => (
            <div key={i} className="card" style={{ textAlign: "center" }}>
              <p style={{ fontSize: 28, marginBottom: 6 }}>{c.icon}</p>
              <p style={{ fontSize: 30, fontWeight: 700, color: c.color, margin: "0 0 4px" }}>{c.value ?? "—"}</p>
              <p style={{ fontSize: 13, color: "var(--slate-500)" }}>{c.label}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Companies Tab                                                                   */
/* ============================================================================= */
function CompaniesTab() {
  const [companies, setCompanies] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch("/api/v1/superadmin/companies")
      .then((d) => setCompanies(d.companies || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Companies</h1>
      <p style={{ fontSize: 14, color: "var(--slate-500)", marginBottom: 28 }}>
        All registered companies on the platform.
      </p>

      {loading ? (
        <p style={{ color: "var(--slate-400)" }}>Loading...</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          <div style={{
            display: "grid",
            gridTemplateColumns: "2fr 1.5fr 1fr 1fr 1fr",
            padding: "8px 16px", fontSize: 11,
            color: "var(--slate-400)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1,
          }}>
            <span>Company</span><span>Slug</span><span>Users</span><span>Conversations</span><span>Active</span>
          </div>
          {companies.map((c: any, i: number) => (
            <div key={i} className="card" style={{
              display: "grid",
              gridTemplateColumns: "2fr 1.5fr 1fr 1fr 1fr",
              padding: "14px 16px", alignItems: "center",
            }}>
              <div>
                <p style={{ fontWeight: 600, fontSize: 14, marginBottom: 2 }}>{c.name}</p>
                <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
                  {c.domain || "—"} · {new Date(c.created_at).toLocaleDateString()}
                </p>
              </div>
              <span style={{ fontFamily: "monospace", fontSize: 13, color: "var(--slate-600)" }}>{c.slug}</span>
              <span style={{ fontWeight: 600 }}>{c.user_count}</span>
              <span style={{ fontWeight: 600 }}>{c.conversation_count}</span>
              <span style={{ fontWeight: 600, color: "#22c55e" }}>{c.active_conversations}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Users Tab                                                                       */
/* ============================================================================= */
function UsersTab() {
  const [users, setUsers] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [roleFilter, setRoleFilter] = useState("");

  useEffect(() => {
    apiFetch("/api/v1/superadmin/users")
      .then((d) => setUsers(d.users || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const roleColors: Record<string, { bg: string; color: string }> = {
    superadmin: { bg: "#ede9fe", color: "#7c3aed" },
    admin:      { bg: "#dbeafe", color: "#1e40af" },
    staff:      { bg: "#dcfce7", color: "#166534" },
  };

  const filtered = roleFilter ? users.filter((u) => u.role === roleFilter) : users;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Users</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>{filtered.length} users</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["", "superadmin", "admin", "staff"].map((r) => (
            <button key={r || "all"} onClick={() => setRoleFilter(r)} style={{
              padding: "7px 14px", borderRadius: 8, border: "1px solid var(--slate-200)",
              background: roleFilter === r ? "var(--primary)" : "white",
              color: roleFilter === r ? "white" : "var(--slate-600)",
              fontSize: 12, cursor: "pointer", fontFamily: "inherit",
            }}>
              {r || "All"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p style={{ color: "var(--slate-400)" }}>Loading...</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {filtered.map((u: any, i: number) => {
            const rc = roleColors[u.role] || { bg: "#f1f5f9", color: "#475569" };
            return (
              <div key={i} className="card" style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px",
              }}>
                <div>
                  <p style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{u.name || u.email}</p>
                  <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
                    {u.email}
                    {u.company_id ? ` · ${u.company_id.slice(0, 12)}...` : " · (global)"}
                  </p>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{
                    fontSize: 11, padding: "3px 9px", borderRadius: 4,
                    fontWeight: 600, background: rc.bg, color: rc.color,
                  }}>{u.role}</span>
                  {!u.enabled && (
                    <span style={{ fontSize: 11, padding: "3px 9px", borderRadius: 4, background: "#fee2e2", color: "#991b1b", fontWeight: 600 }}>
                      disabled
                    </span>
                  )}
                  <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
                    {new Date(u.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Conversations Tab                                                               */
/* ============================================================================= */
function ConversationsTab() {
  const [conversations, setConversations] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState("active");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    apiFetch(`/api/v1/superadmin/conversations${qs}`)
      .then((d) => setConversations(d.conversations || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [statusFilter]);

  const statusColors: Record<string, { bg: string; color: string }> = {
    active:   { bg: "#dcfce7", color: "#166534" },
    resolved: { bg: "#dbeafe", color: "#1e40af" },
    archived: { bg: "#f1f5f9", color: "#475569" },
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Conversations</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>{conversations.length} conversations</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {["active", "resolved", "all"].map((s) => (
            <button key={s} onClick={() => setStatusFilter(s === "all" ? "" : s)} style={{
              padding: "7px 14px", borderRadius: 8, border: "1px solid var(--slate-200)",
              background: (statusFilter === s || (s === "all" && !statusFilter)) ? "var(--primary)" : "white",
              color: (statusFilter === s || (s === "all" && !statusFilter)) ? "white" : "var(--slate-600)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit",
            }}>
              {s === "active" ? "Active" : s === "resolved" ? "Resolved" : "All"}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p style={{ color: "var(--slate-400)" }}>Loading...</p>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {conversations.map((c: any, i: number) => {
            const sc = statusColors[c.status] || statusColors.archived;
            return (
              <div key={i} className="card" style={{
                display: "grid", gridTemplateColumns: "auto 2fr 2fr 1fr 1fr",
                padding: "12px 16px", gap: 12, alignItems: "center",
              }}>
                <span style={{
                  fontSize: 11, padding: "3px 9px", borderRadius: 4,
                  fontWeight: 600, background: sc.bg, color: sc.color, whiteSpace: "nowrap",
                }}>{c.status}</span>
                <div>
                  <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 1 }}>Company</p>
                  <p style={{ fontSize: 13, fontFamily: "monospace" }}>{(c.company_id || "").slice(0, 16)}...</p>
                </div>
                <div>
                  <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 1 }}>Customer</p>
                  <p style={{ fontSize: 13, fontFamily: "monospace" }}>{(c.customer_id || "").slice(0, 16)}...</p>
                </div>
                <div>
                  <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 1 }}>Assigned</p>
                  <p style={{ fontSize: 12 }}>{c.assigned_staff_id ? "Yes" : "—"}</p>
                </div>
                <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
                  {new Date(c.created_at).toLocaleDateString()}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Audit Tab                                                                       */
/* ============================================================================= */
function AuditTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [limit, setLimit] = useState(100);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    apiFetch(`/api/v1/superadmin/audit-logs?limit=${limit}`)
      .then((d) => setLogs(d.audit_logs || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [limit]);

  const eventColors: Record<string, { bg: string; color: string }> = {
    rag_generation:        { bg: "#dcfce7", color: "#166534" },
    escalation:            { bg: "#fee2e2", color: "#991b1b" },
    clarification:         { bg: "#fef3c7", color: "#92400e" },
    intent_classification: { bg: "#dbeafe", color: "#1e40af" },
    ticket_resolved:       { bg: "#ede9fe", color: "#7c3aed" },
    conversation_resolved: { bg: "#ede9fe", color: "#7c3aed" },
    ingestion:             { bg: "#f3e8ff", color: "#6b21a8" },
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Global Audit Logs</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>All events across all companies.</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {[50, 100, 250].map((n) => (
            <button key={n} onClick={() => setLimit(n)} style={{
              padding: "7px 14px", borderRadius: 8, border: "1px solid var(--slate-200)",
              background: limit === n ? "var(--primary)" : "white",
              color: limit === n ? "white" : "var(--slate-600)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit",
            }}>
              Last {n}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p style={{ color: "var(--slate-400)" }}>Loading...</p>
      ) : logs.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p style={{ color: "var(--slate-400)", fontSize: 14 }}>No audit logs yet.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          {logs.map((log: any, i: number) => {
            const ec = eventColors[log.event_type] || { bg: "#f1f5f9", color: "#475569" };
            return (
              <div key={i} className="card" style={{ padding: "12px 18px" }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                    <span style={{ fontSize: 11, padding: "2px 9px", borderRadius: 4, fontWeight: 600, background: ec.bg, color: ec.color }}>
                      {log.event_type}
                    </span>
                    {log.company_id && (
                      <span style={{ fontSize: 11, color: "var(--slate-400)", fontFamily: "monospace" }}>
                        {log.company_id.slice(0, 12)}...
                      </span>
                    )}
                    {log.confidence > 0 && (
                      <span style={{ fontSize: 11, color: "var(--slate-400)" }}>
                        {(log.confidence * 100).toFixed(0)}% confidence
                      </span>
                    )}
                  </div>
                  <span style={{ fontSize: 11, color: "var(--slate-400)", whiteSpace: "nowrap", marginLeft: 8 }}>
                    {log.latency_ms}ms · {new Date(log.created_at).toLocaleString()}
                  </span>
                </div>
                <p style={{ fontSize: 13, color: "var(--slate-700)", marginBottom: 2 }}>
                  <strong style={{ color: "var(--slate-500)" }}>Q: </strong>
                  {log.request_summary?.substring(0, 120)}{log.request_summary?.length > 120 ? "…" : ""}
                </p>
                <p style={{ fontSize: 13, color: "var(--slate-500)" }}>
                  <strong>A: </strong>
                  {log.response_summary?.substring(0, 120)}{log.response_summary?.length > 120 ? "…" : ""}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
