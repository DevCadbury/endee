"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   /admin — Admin Management Panel
   Full-control view: system stats, all tickets (all statuses), KB CRUD,
   audit log, and an embedded live chat tester — all scoped to the company.
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

async function apiFetch(path: string, opts: RequestInit = {}): Promise<any> {
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

type AdminTab = "stats" | "tickets" | "conversations" | "kb" | "audit" | "test" | "staff" | "settings" | "kb_entries";

/* ============================================================================= */
export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<AdminTab>("stats");
  const [email, setEmail] = useState("");

  useEffect(() => {
    const auth = getAuth();
    setEmail(auth.email);
    if (!auth.token) router.push("/login");
  }, [router]);

  const tabs: { key: AdminTab; label: string; icon: string }[] = [
    { key: "stats",         label: "System Stats",    icon: "📈" },
    { key: "conversations", label: "Conversations",   icon: "💬" },
    { key: "tickets",       label: "All Tickets",     icon: "🎫" },
    { key: "staff",         label: "Staff",           icon: "👥" },
    { key: "settings",      label: "Settings",        icon: "⚙️" },
    { key: "kb_entries",    label: "KB Entries",      icon: "🧠" },
    { key: "kb",            label: "Knowledge Base",  icon: "📚" },
    { key: "audit",         label: "Audit Log",       icon: "📋" },
    { key: "test",          label: "Test Widget",     icon: "🧪" },
  ];

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "#0f172a" }}>
      {/* ---- Dark Sidebar ---- */}
      <aside style={{
        width: 240, flexShrink: 0,
        background: "#0f172a", borderRight: "1px solid #1e293b",
        padding: "20px 0", display: "flex", flexDirection: "column",
      }}>
        {/* Logo */}
        <div style={{ padding: "0 20px 20px", display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{
            width: 32, height: 32, borderRadius: 8, background: "var(--primary)",
            display: "flex", alignItems: "center", justifyContent: "center",
            color: "white", fontWeight: 800, fontSize: 15,
          }}>R</div>
          <div>
            <p style={{ fontWeight: 700, fontSize: 16, color: "white", margin: 0 }}>ResolveAI</p>
            <p style={{ fontSize: 10, color: "#4ade80", margin: 0, fontWeight: 600, letterSpacing: 1 }}>ADMIN</p>
          </div>
        </div>

        {/* Back link */}
        <div style={{ padding: "0 20px 16px" }}>
          <a href="/dashboard" style={{
            display: "flex", alignItems: "center", gap: 6,
            color: "#475569", textDecoration: "none", fontSize: 12,
            padding: "6px 8px", borderRadius: 6,
            background: "transparent",
          }}>
            ← Back to Dashboard
          </a>
        </div>

        <div style={{ height: 1, background: "#1e293b", margin: "0 20px 16px" }} />

        {/* Tabs */}
        <nav style={{ flex: 1 }}>
          {tabs.map((t) => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              display: "flex", alignItems: "center", gap: 10,
              width: "100%", padding: "10px 20px", border: "none",
              background: tab === t.key ? "rgba(74,222,128,0.1)" : "transparent",
              color: tab === t.key ? "#4ade80" : "#64748b",
              fontWeight: tab === t.key ? 600 : 400,
              fontSize: 14, cursor: "pointer",
              borderLeft: tab === t.key ? "3px solid #4ade80" : "3px solid transparent",
              fontFamily: "inherit",
              transition: "all 0.15s",
            }}>
              <span style={{ fontSize: 16 }}>{t.icon}</span>
              {t.label}
            </button>
          ))}
        </nav>

        {/* Footer */}
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
        {tab === "stats"         && <AdminStatsTab />}
        {tab === "conversations" && <AdminConversationsTab />}
        {tab === "tickets"       && <AdminTicketsTab />}
        {tab === "staff"      && <AdminStaffTab />}
        {tab === "settings"   && <AdminSettingsTab />}
        {tab === "kb_entries" && <AdminKBEntriesTab />}
        {tab === "kb"         && <AdminKBTab />}
        {tab === "audit"      && <AdminAuditTab />}
        {tab === "test"       && <AdminTestTab />}
      </main>
    </div>
  );
}

/* ============================================================================= */
/* Stats Tab                                                                      */
/* ============================================================================= */
function AdminStatsTab() {
  const [stats, setStats] = useState<any>(null);

  useEffect(() => {
    apiFetch("/api/v1/dashboard/stats").then(setStats).catch(console.error);
  }, []);

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>System Stats</h1>
      <p style={{ fontSize: 14, color: "var(--slate-500)", marginBottom: 28 }}>
        Real-time performance metrics for your AI support system.
      </p>

      {!stats ? (
        <p style={{ color: "var(--slate-400)" }}>Loading stats…</p>
      ) : (
        <>
          {/* Stat cards */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 16, marginBottom: 28 }}>
            {[
              { label: "Total Chats",      value: stats.total_chats,      icon: "💬", color: "#3b82f6" },
              { label: "Auto-Resolved",    value: stats.auto_resolved,    icon: "✅", color: "#22c55e" },
              { label: "Escalated",        value: stats.escalated,        icon: "🚨", color: "#ef4444" },
              { label: "Clarified",        value: stats.clarified,        icon: "❓", color: "#f59e0b" },
              { label: "Pending Tickets",  value: stats.pending_tickets,  icon: "⏳", color: "#f59e0b" },
              { label: "KB Documents",     value: stats.total_documents,  icon: "📄", color: "#8b5cf6" },
            ].map((c, i) => (
              <div key={i} className="card" style={{ textAlign: "center" }}>
                <p style={{ fontSize: 28, marginBottom: 6 }}>{c.icon}</p>
                <p style={{ fontSize: 32, fontWeight: 700, color: c.color, margin: "0 0 4px" }}>{c.value ?? "—"}</p>
                <p style={{ fontSize: 13, color: "var(--slate-500)" }}>{c.label}</p>
              </div>
            ))}
          </div>

          {/* Rate bars */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
            {[
              { label: "Auto-Resolve Rate", value: stats.auto_resolve_rate, color: "#22c55e" },
              { label: "Escalation Rate",   value: stats.escalation_rate,   color: "#ef4444" },
            ].map((r) => (
              <div key={r.label} className="card">
                <p style={{ fontSize: 13, fontWeight: 600, color: "var(--slate-500)", textTransform: "uppercase", letterSpacing: 1, marginBottom: 12 }}>
                  {r.label}
                </p>
                <div style={{ height: 10, background: "var(--slate-100)", borderRadius: 5, overflow: "hidden", marginBottom: 8 }}>
                  <div style={{
                    height: "100%", width: `${Math.min(r.value, 100)}%`,
                    background: r.color, borderRadius: 5,
                    transition: "width 0.8s ease",
                  }} />
                </div>
                <p style={{ fontSize: 30, fontWeight: 700, color: r.color, margin: 0 }}>{r.value}%</p>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Tickets Tab                                                                    */
/* ============================================================================= */
function AdminTicketsTab() {
  const [tickets, setTickets] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "pending" | "resolved" | "assigned">("");
  const [resolutions, setResolutions] = useState<Record<string, string>>({});
  const [resolving, setResolving] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [resolveMsg, setResolveMsg] = useState<string | null>(null);

  const loadTickets = () => {
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    apiFetch(`/api/v1/dashboard/tickets${qs}`).then((d) => setTickets(d.tickets || [])).catch(console.error);
  };

  useEffect(() => { loadTickets(); }, [statusFilter]);

  const resolveTicket = async (id: string) => {
    const resolution = resolutions[id]?.trim();
    if (!resolution) return;
    setResolving(id);
    setResolveMsg(null);
    try {
      const data = await apiFetch(`/api/v1/dashboard/tickets/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ resolution, ingest_to_kb: true }),
      });
      if (data.kb_ingested) {
        setResolveMsg("Resolved and ingested into KB. The AI will now auto-resolve similar questions.");
      } else {
        setResolveMsg("error:Ticket resolved but KB ingestion failed. Check backend logs.");
      }
      loadTickets();
    } catch (err: any) {
      setResolveMsg(`error:${err.message || "Failed to resolve ticket"}`);
    }
    setResolving(null);
  };

  const statusBadge = (status: string) => {
    const styles: Record<string, { bg: string; color: string }> = {
      pending:  { bg: "#fef3c7", color: "#92400e" },
      resolved: { bg: "#dcfce7", color: "#166534" },
      assigned: { bg: "#dbeafe", color: "#1e40af" },
    };
    const s = styles[status] || { bg: "#f1f5f9", color: "#475569" };
    return (
      <span style={{ fontSize: 11, padding: "3px 9px", borderRadius: 4, fontWeight: 600, background: s.bg, color: s.color }}>
        {status}
      </span>
    );
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>All Tickets</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>{tickets.length} ticket{tickets.length !== 1 ? "s" : ""} found</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {(["", "pending", "assigned", "resolved"] as const).map((s) => (
            <button key={s} onClick={() => setStatusFilter(s)} style={{
              padding: "7px 14px", borderRadius: 8, border: "1px solid var(--slate-200)",
              background: statusFilter === s ? "var(--primary)" : "white",
              color: statusFilter === s ? "white" : "var(--slate-600)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: statusFilter === s ? 600 : 400,
            }}>
              {s || "All"}
            </button>
          ))}
        </div>
      </div>

      {resolveMsg && (() => {
        const isError = resolveMsg.startsWith("error:");
        const msg = isError ? resolveMsg.slice(6) : resolveMsg;
        return (
          <div style={{
            padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 16,
            background: isError ? "#fef2f2" : "#dcfce7",
            color: isError ? "#991b1b" : "#166534",
            border: `1px solid ${isError ? "#fecaca" : "#86efac"}`,
          }}>
            {isError ? "⚠ " : "✅ "}{msg}
          </div>
        );
      })()}

      {tickets.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p style={{ fontSize: 20, marginBottom: 8 }}>🎉</p>
          <p style={{ color: "var(--slate-500)", fontSize: 14 }}>No tickets match this filter.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {tickets.map((t: any) => (
            <div key={t._id} className="card" style={{ padding: "16px 20px" }}>
              {/* Header row */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 10 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  {statusBadge(t.status)}
                  <span style={{ fontSize: 12, color: "var(--slate-400)", fontFamily: "monospace" }}>
                    #{t._id?.slice(-8)}
                  </span>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ fontSize: 12, color: "var(--slate-400)" }}>
                    {new Date(t.created_at).toLocaleString()}
                  </span>
                  <button
                    onClick={() => setExpandedId(expandedId === t._id ? null : t._id)}
                    style={{ background: "none", border: "none", color: "var(--slate-400)", cursor: "pointer", fontSize: 12, fontFamily: "inherit" }}
                  >
                    {expandedId === t._id ? "▲ Less" : "▼ More"}
                  </button>
                </div>
              </div>

              {/* Message */}
              <div style={{ background: "var(--slate-50)", padding: "10px 14px", borderRadius: 8, fontSize: 13, color: "var(--slate-700)", marginBottom: 6 }}>
                {t.customer_message}
              </div>

              {/* Expanded content */}
              {expandedId === t._id && (
                <div style={{ marginTop: 10 }}>
                  {t.ai_response && (
                    <div style={{ marginBottom: 10 }}>
                      <p style={{ fontSize: 12, fontWeight: 600, color: "var(--slate-400)", marginBottom: 4 }}>AI RESPONSE</p>
                      <div style={{ background: "#f0fdf4", padding: "8px 12px", borderRadius: 6, fontSize: 12, color: "#166534" }}>
                        {t.ai_response}
                      </div>
                    </div>
                  )}
                  {t.ai_context && (
                    <div style={{ marginBottom: 10 }}>
                      <p style={{ fontSize: 12, fontWeight: 600, color: "var(--slate-400)", marginBottom: 4 }}>AI CONTEXT</p>
                      <p style={{ fontSize: 12, color: "var(--slate-500)" }}>{t.ai_context}</p>
                    </div>
                  )}
                  {t.status === "resolved" && t.resolution && (
                    <div style={{ marginBottom: 10 }}>
                      <p style={{ fontSize: 12, fontWeight: 600, color: "var(--slate-400)", marginBottom: 4 }}>RESOLUTION</p>
                      <div style={{ background: "#eff6ff", padding: "8px 12px", borderRadius: 6, fontSize: 12, color: "#1e40af" }}>
                        {t.resolution}
                      </div>
                    </div>
                  )}

                  {/* Resolve form for pending tickets */}
                  {t.status === "pending" && (
                    <div style={{ marginTop: 10 }}>
                      <p style={{ fontSize: 12, fontWeight: 600, color: "var(--slate-400)", marginBottom: 6 }}>RESOLVE & LEARN</p>
                      <textarea
                        className="input"
                        rows={2}
                        placeholder="Enter resolution text…"
                        value={resolutions[t._id] || ""}
                        onChange={(e) => setResolutions((p) => ({ ...p, [t._id]: e.target.value }))}
                        style={{ marginBottom: 8, fontSize: 13, fontFamily: "inherit", resize: "vertical" }}
                      />
                      <button
                        className="btn btn-primary"
                        onClick={() => resolveTicket(t._id)}
                        disabled={resolving === t._id || !resolutions[t._id]?.trim()}
                        style={{ fontSize: 13 }}
                      >
                        {resolving === t._id ? "Resolving…" : "Resolve & Ingest to KB"}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Knowledge Base Tab                                                              */
/* ============================================================================= */
function AdminKBTab() {
  const [docs, setDocs] = useState<any[]>([]);
  const [form, setForm] = useState({ title: "", content: "", source_type: "text", category: "general", tags: "" });
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [pdfTitle, setPdfTitle] = useState("");
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [activeForm, setActiveForm] = useState<"text" | "pdf">("text");
  const [ingestResult, setIngestResult] = useState<string | null>(null);

  const loadDocs = () => {
    apiFetch("/api/v1/kb/documents").then((d) => setDocs(d.documents || [])).catch(console.error);
  };
  useEffect(() => { loadDocs(); }, []);

  const handleTextIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (form.content.trim().length < 30) {
      setIngestResult("error:Content is too short. Paste at least a few sentences for meaningful ingestion.");
      return;
    }
    setUploading(true);
    setIngestResult(null);
    try {
      const data = await apiFetch("/api/v1/kb/ingest", { method: "POST", body: JSON.stringify(form) });
      if (!data.chunk_count || data.chunk_count === 0) {
        setIngestResult("error:No chunks generated. Content may be too short or got cleaned away. Paste longer text (at least a paragraph).");
      } else {
        setIngestResult(`Ingested ${data.chunk_count} chunk${data.chunk_count !== 1 ? "s" : ""} · ID: ${data.doc_id || data.mongo_id}`);
        setForm({ title: "", content: "", source_type: "text", category: "general", tags: "" });
        loadDocs();
      }
    } catch (err: any) {
      setIngestResult(`error:${err.message || "Ingestion failed"}`);
    }
    setUploading(false);
  };

  const handlePdfIngest = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!pdfFile || !pdfTitle.trim()) return;
    setUploading(true);
    setIngestResult(null);
    try {
      const fd = new FormData();
      fd.append("file", pdfFile);
      fd.append("title", pdfTitle);
      fd.append("category", "general");
      const data = await apiFetch("/api/v1/kb/ingest/pdf", { method: "POST", body: fd });
      if (!data.chunk_count || data.chunk_count === 0) {
        setIngestResult("error:No text could be extracted from PDF. Try a different file.");
      } else {
        setIngestResult(`Ingested PDF: ${data.chunk_count} chunk${data.chunk_count !== 1 ? "s" : ""}`);
        setPdfFile(null);
        setPdfTitle("");
        loadDocs();
      }
    } catch (err: any) {
      setIngestResult(`error:${err.message || "PDF ingestion failed"}`);
    }
    setUploading(false);
  };

  const deleteDoc = async (docId: string) => {
    if (!confirm("Delete this document and all its chunks from the knowledge base?")) return;
    setDeleting(docId);
    try {
      await apiFetch(`/api/v1/kb/documents/${docId}`, { method: "DELETE" });
      loadDocs();
    } catch (err) { console.error(err); }
    setDeleting(null);
  };

  const sourceTypeColors: Record<string, string> = {
    text: "#3b82f6", pdf: "#ef4444", slack: "#f59e0b",
    email: "#8b5cf6", confluence: "#0ea5e9", notion: "#1e293b",
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Knowledge Base</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>{docs.length} document{docs.length !== 1 ? "s" : ""} indexed</p>
        </div>
      </div>

      {/* Ingest form */}
      <div className="card" style={{ marginBottom: 24 }}>
        <div style={{ display: "flex", gap: 8, marginBottom: 16 }}>
          {(["text", "pdf"] as const).map((type) => (
            <button key={type} onClick={() => { setActiveForm(type); setIngestResult(null); }} style={{
              padding: "7px 16px", borderRadius: 8, border: "1px solid var(--slate-200)",
              background: activeForm === type ? "var(--primary)" : "white",
              color: activeForm === type ? "white" : "var(--slate-600)",
              fontSize: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: activeForm === type ? 600 : 400,
            }}>
              {type === "text" ? "📝 Text / Markdown" : "📄 PDF Upload"}
            </button>
          ))}
        </div>

        {ingestResult && (() => {
          const isError = ingestResult.startsWith("error:");
          const msg = isError ? ingestResult.slice(6) : ingestResult;
          return (
            <div style={{
              padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 14,
              background: isError ? "#fef2f2" : "#dcfce7",
              color: isError ? "#991b1b" : "#166534",
              border: `1px solid ${isError ? "#fecaca" : "#86efac"}`,
            }}>
              {isError ? "⚠ " : "✅ "}{msg}
            </div>
          );
        })()}

        {activeForm === "text" ? (
          <form onSubmit={handleTextIngest} style={{ display: "grid", gap: 12 }}>
            <input className="input" placeholder="Document title" value={form.title}
              onChange={(e) => setForm((p) => ({ ...p, title: e.target.value }))} required />
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 12 }}>
              <select className="input" value={form.source_type}
                onChange={(e) => setForm((p) => ({ ...p, source_type: e.target.value }))}>
                <option value="text">Text</option>
                <option value="slack">Slack</option>
                <option value="email">Email</option>
                <option value="confluence">Confluence</option>
                <option value="notion">Notion</option>
                <option value="drive">Drive</option>
              </select>
              <select className="input" value={form.category}
                onChange={(e) => setForm((p) => ({ ...p, category: e.target.value }))}>
                <option value="general">General</option>
                <option value="billing">Billing</option>
                <option value="technical">Technical</option>
                <option value="account">Account</option>
                <option value="product">Product</option>
              </select>
              <input className="input" placeholder="Tags (comma-separated)" value={form.tags}
                onChange={(e) => setForm((p) => ({ ...p, tags: e.target.value }))} />
            </div>
            <textarea className="input" rows={6} placeholder="Paste document content…" value={form.content}
              onChange={(e) => setForm((p) => ({ ...p, content: e.target.value }))} required
              style={{ resize: "vertical", fontFamily: "inherit" }} />
            <button className="btn btn-primary" type="submit" disabled={uploading} style={{ justifySelf: "start" }}>
              {uploading ? "Ingesting…" : "Ingest Document"}
            </button>
          </form>
        ) : (
          <form onSubmit={handlePdfIngest} style={{ display: "grid", gap: 12 }}>
            <input className="input" placeholder="Document title" value={pdfTitle}
              onChange={(e) => setPdfTitle(e.target.value)} required />
            <div style={{
              border: "2px dashed var(--slate-200)", borderRadius: 8,
              padding: "24px", textAlign: "center", cursor: "pointer",
              background: pdfFile ? "#f0fdf4" : "var(--slate-50)",
            }}>
              <input type="file" accept=".pdf" id="pdf-upload" style={{ display: "none" }}
                onChange={(e) => setPdfFile(e.target.files?.[0] || null)} />
              <label htmlFor="pdf-upload" style={{ cursor: "pointer" }}>
                <p style={{ fontSize: 24, marginBottom: 6 }}>📄</p>
                <p style={{ fontSize: 14, color: pdfFile ? "#166534" : "var(--slate-500)" }}>
                  {pdfFile ? `✅ ${pdfFile.name} (${(pdfFile.size / 1024).toFixed(1)} KB)` : "Click to select a PDF file"}
                </p>
              </label>
            </div>
            <button className="btn btn-primary" type="submit" disabled={uploading || !pdfFile || !pdfTitle.trim()} style={{ justifySelf: "start" }}>
              {uploading ? "Uploading…" : "Upload & Ingest PDF"}
            </button>
          </form>
        )}
      </div>

      {/* Document list */}
      <div className="card">
        <h3 style={{ fontSize: 16, marginBottom: 16, fontWeight: 600 }}>
          Indexed Documents ({docs.length})
        </h3>
        {docs.length === 0 ? (
          <p style={{ color: "var(--slate-400)", fontSize: 14 }}>No documents yet. Upload one above.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {docs.map((doc: any) => (
              <div key={doc._id} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px", background: "var(--slate-50)", borderRadius: 8,
                border: "1px solid var(--slate-100)",
              }}>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontWeight: 500, fontSize: 14, marginBottom: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    {doc.title}
                  </p>
                  <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
                    {doc.chunk_count} chunks · {doc.category || "general"}
                    {doc.tags && ` · ${doc.tags}`}
                    {doc.created_at && ` · ${new Date(doc.created_at).toLocaleDateString()}`}
                  </p>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
                  <span style={{
                    fontSize: 11, padding: "3px 9px", borderRadius: 4, fontWeight: 600,
                    background: (sourceTypeColors[doc.source_type] || "#64748b") + "18",
                    color: sourceTypeColors[doc.source_type] || "#64748b",
                  }}>{doc.source_type}</span>
                  <button
                    onClick={() => deleteDoc(doc._id)}
                    disabled={deleting === doc._id}
                    style={{
                      padding: "5px 12px", borderRadius: 6, border: "1px solid #fecaca",
                      background: "white", color: "#ef4444", fontSize: 12,
                      cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    {deleting === doc._id ? "…" : "Delete"}
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================================= */
/* Audit Tab                                                                       */
/* ============================================================================= */
function AdminAuditTab() {
  const [logs, setLogs] = useState<any[]>([]);
  const [limit, setLimit] = useState(100);

  useEffect(() => {
    apiFetch(`/api/v1/dashboard/audit?limit=${limit}`).then((d) => setLogs(d.audit_logs || [])).catch(console.error);
  }, [limit]);

  const eventColors: Record<string, { bg: string; color: string }> = {
    rag_generation:       { bg: "#dcfce7", color: "#166534" },
    escalation:           { bg: "#fee2e2", color: "#991b1b" },
    clarification:        { bg: "#fef3c7", color: "#92400e" },
    intent_classification:{ bg: "#dbeafe", color: "#1e40af" },
    ingestion:            { bg: "#f3e8ff", color: "#6b21a8" },
    ticket_resolved:      { bg: "#f0fdf4", color: "#166534" },
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Audit Log</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>Complete event history for your company.</p>
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

      {logs.length === 0 ? (
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
                    <span style={{
                      fontSize: 11, padding: "2px 9px", borderRadius: 4, fontWeight: 600,
                      background: ec.bg, color: ec.color,
                    }}>{log.event_type}</span>
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
                {log.model && (
                  <p style={{ fontSize: 11, color: "var(--slate-400)", marginTop: 4 }}>
                    Model: {log.model}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Test Widget Tab (embedded)                                                      */
/* ============================================================================= */
function AdminTestTab() {
  type MsgRole = "user" | "ai" | "staff";
  type Msg = { role: MsgRole; text: string; ts: string; action?: string; sources?: string[]; debug?: any };

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
  const WS_URL  = API_URL.replace(/^http/, "ws");

  const [slug, setSlug] = useState("");
  const sessionId = useRef("admin-test-" + Math.random().toString(36).slice(2));

  const [wsStatus, setWsStatus]     = useState<"connecting"|"connected"|"offline">("offline");
  const [staffOnline, setStaffOnline] = useState(0);
  const [convId, setConvId]         = useState("");
  const [messages, setMessages]     = useState<Msg[]>([]);
  const [input, setInput]           = useState("");
  const [isTyping, setIsTyping]     = useState(false);
  const [isResolved, setIsResolved] = useState(false);
  const [showDebug, setShowDebug]   = useState(false);
  const [debugLog, setDebugLog]     = useState<any[]>([]);

  const wsRef          = useRef<WebSocket | null>(null);
  const typingTORef    = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectTORef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  /* Scroll to bottom whenever messages/typing change */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  /* Read slug from localStorage on client mount */
  useEffect(() => {
    const s = localStorage.getItem("slug") || "";
    setSlug(s);
  }, []);

  /* Connect WebSocket when slug is ready */
  useEffect(() => {
    if (!slug) { setWsStatus("offline"); return; }
    connectWS();
    return () => {
      wsRef.current?.close();
      if (reconnectTORef.current) clearTimeout(reconnectTORef.current);
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  function connectWS() {
    if (!slug) return;
    setWsStatus("connecting");
    const ws = new WebSocket(`${WS_URL}/api/v1/ws/widget/${slug}?session_id=${sessionId.current}`);
    wsRef.current = ws;

    ws.onmessage = (evt) => {
      try { handleWsEvent(JSON.parse(evt.data)); } catch {}
    };
    ws.onclose = () => {
      setWsStatus("offline");
      if (!isResolved) {
        reconnectTORef.current = setTimeout(connectWS, 3000);
      }
    };
    ws.onerror = () => ws.close();
  }

  function handleWsEvent(data: any) {
    setDebugLog((prev) => [...prev.slice(-49), { ts: new Date().toISOString(), ...data }]);
    const t = data.type;

    if (t === "connected") {
      setWsStatus("connected");
      setStaffOnline(data.staff_online || 0);
      setConvId(data.conv_id || "");
      if (data.messages?.length) {
        setMessages(data.messages.map((m: any) => ({
          role: (m.sender_type === "customer" ? "user" : m.sender_type === "ai" ? "ai" : "staff") as MsgRole,
          text: m.content,
          ts: m.created_at || new Date().toISOString(),
          action: m.metadata?.action,
          sources: m.metadata?.sources,
          debug: m,
        })));
      } else {
        setMessages([{ role: "ai", text: "Hello! Ask anything to test your AI support agent.", ts: new Date().toISOString(), debug: data }]);
      }

    } else if (t === "message") {
      setIsTyping(false);
      if (data.sender_type !== "customer") {
        setMessages((prev) => [...prev, {
          role: (data.sender_type === "ai" ? "ai" : "staff") as MsgRole,
          text: data.content,
          ts: data.created_at || new Date().toISOString(),
          action: data.metadata?.action,
          sources: data.metadata?.sources,
          debug: data,
        }]);
      }

    } else if (t === "message_ack") {
      /* Optimistically shown — nothing to do */

    } else if (t === "ai_thinking") {
      setIsTyping(true);

    } else if (t === "typing") {
      if (data.sender_type !== "customer") {
        setIsTyping(true);
        if (typingTORef.current) clearTimeout(typingTORef.current);
        typingTORef.current = setTimeout(() => setIsTyping(false), 4000);
      }

    } else if (t === "conversation_status") {
      if (data.new_status === "resolved") {
        setIsTyping(false);
        setIsResolved(true);
      }

    } else if (t === "presence") {
      if (data.role === "staff") {
        setStaffOnline((prev) => data.event === "joined" ? prev + 1 : Math.max(0, prev - 1));
      }
    }
  }

  const sendMessage = (text?: string) => {
    const msg = (text ?? input).trim();
    if (!msg || isResolved) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", text: msg, ts: new Date().toISOString() }]);
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: "message", content: msg }));
    }
  };

  const resetChat = () => {
    setMessages([]);
    setIsResolved(false);
    setIsTyping(false);
    setDebugLog([]);
    setConvId("");
    sessionId.current = "admin-test-" + Date.now().toString(36);
    wsRef.current?.close();
    wsRef.current = null;
    connectWS();
  };

  const ACTION_STYLES: Record<string, { bg: string; color: string; label: string }> = {
    auto_reply: { bg: "#dcfce7", color: "#166534", label: "Auto Resolved" },
    clarify:    { bg: "#fef3c7", color: "#92400e", label: "Clarifying" },
    escalate:   { bg: "#fee2e2", color: "#991b1b", label: "Escalated" },
  };

  const statusLabel = wsStatus === "connected"
    ? (staffOnline > 0 ? `${staffOnline} staff online` : "AI Active")
    : wsStatus === "connecting" ? "Connecting…" : "Offline – reconnecting…";
  const statusColor = wsStatus === "connected" ? "#4ade80" : wsStatus === "connecting" ? "#fbbf24" : "#f87171";

  if (!slug) {
    return (
      <div style={{ padding: 32, color: "var(--slate-500)", textAlign: "center" }}>
        <p style={{ fontSize: 32, marginBottom: 8 }}>⚠️</p>
        <p style={{ fontSize: 14 }}>Company slug not found in session. Please log out and log in again.</p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Test Widget</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>
            Send real messages to your AI. Staff replies appear here in real-time.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button onClick={resetChat} style={{
            padding: "8px 16px", borderRadius: 8, border: "1px solid var(--slate-200)",
            background: "white", color: "var(--slate-700)", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
          }}>Clear</button>
          <button onClick={() => setShowDebug(!showDebug)} style={{
            padding: "8px 16px", borderRadius: 8, border: "1px solid var(--slate-200)",
            background: showDebug ? "var(--slate-900)" : "white",
            color: showDebug ? "white" : "var(--slate-700)", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
          }}>{showDebug ? "Hide Debug" : "Show Debug"}</button>
        </div>
      </div>

      <div style={{ display: "flex", gap: 16 }}>
        {/* Chat panel */}
        <div style={{ flex: 1, background: "white", borderRadius: 12, border: "1px solid var(--slate-200)", overflow: "hidden", display: "flex", flexDirection: "column", minHeight: 500 }}>
          {/* Header */}
          <div style={{ padding: "14px 20px", background: "var(--primary)", color: "white", display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{ fontSize: 20 }}>🤖</span>
            <div style={{ flex: 1 }}>
              <p style={{ fontWeight: 600, margin: 0 }}>AI Support Agent</p>
              <p style={{ fontSize: 12, opacity: 0.85, margin: 0, display: "flex", alignItems: "center", gap: 4 }}>
                <span style={{ width: 7, height: 7, borderRadius: "50%", background: statusColor, display: "inline-block" }} />
                {statusLabel}
                {convId && <span style={{ marginLeft: 8, fontFamily: "monospace", opacity: 0.7 }}>#{convId.slice(-8)}</span>}
              </p>
            </div>
          </div>

          {/* Messages */}
          <div style={{ flex: 1, overflowY: "auto", padding: 16, display: "flex", flexDirection: "column", gap: 10 }}>
            {messages.length === 0 && (
              <div style={{ textAlign: "center", padding: "32px 16px", color: "var(--slate-400)" }}>
                <p style={{ fontSize: 32, marginBottom: 8 }}>💬</p>
                <p style={{ fontSize: 14 }}>Type a message to test your AI support agent.</p>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} style={{ display: "flex", justifyContent: msg.role === "user" ? "flex-end" : "flex-start" }}>
                <div style={{ maxWidth: "76%" }}>
                  <div style={{
                    padding: "10px 14px",
                    background: msg.role === "user" ? "var(--primary)"
                              : msg.role === "staff" ? "#dcfce7" : "var(--slate-100)",
                    color: msg.role === "user" ? "white"
                         : msg.role === "staff" ? "#166534" : "var(--slate-800)",
                    borderRadius: msg.role === "user" ? "14px 14px 4px 14px" : "14px 14px 14px 4px",
                    fontSize: 13.5, lineHeight: 1.5,
                  }}>{msg.text}</div>
                  <p style={{ fontSize: 10, color: "var(--slate-400)", margin: "3px 4px 0", textAlign: msg.role === "user" ? "right" : "left" }}>
                    {msg.ts ? new Date(msg.ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : ""}
                  </p>
                  {(msg.action || msg.role === "staff" || msg.debug) && (
                    <div style={{ marginTop: 4, display: "flex", gap: 5, flexWrap: "wrap" }}>
                      {msg.action && ACTION_STYLES[msg.action] && (
                        <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 4, fontWeight: 600, background: ACTION_STYLES[msg.action].bg, color: ACTION_STYLES[msg.action].color }}>
                          {ACTION_STYLES[msg.action].label}
                        </span>
                      )}
                      {msg.role === "staff" && (
                        <span style={{ fontSize: 11, padding: "2px 7px", borderRadius: 4, fontWeight: 600, background: "#dbeafe", color: "#1e40af" }}>
                          👤 Staff
                        </span>
                      )}
                      {msg.sources?.length ? (
                        <span style={{ fontSize: 11, color: "var(--slate-400)" }}>📄 {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}</span>
                      ) : null}
                      {msg.debug && (
                        <button onClick={() => setDebugLog((prev) => [msg.debug, ...prev.slice(0, 49)])} style={{
                          fontSize: 11, padding: "2px 7px", borderRadius: 4, border: "1px solid var(--slate-200)",
                          background: "white", cursor: "pointer", fontFamily: "inherit", color: "var(--slate-500)",
                        }}>⚙ Debug</button>
                      )}
                    </div>
                  )}
                </div>
              </div>
            ))}

            {/* Typing indicator */}
            {isTyping && (
              <div style={{ display: "flex", gap: 4, padding: "10px 14px", background: "var(--slate-100)", borderRadius: "14px 14px 14px 4px", alignSelf: "flex-start" }}>
                {[0, 1, 2].map((j) => (
                  <div key={j} style={{ width: 7, height: 7, borderRadius: "50%", background: "var(--slate-400)", animation: `blink 1.4s ${j * 0.2}s infinite` }} />
                ))}
                <style>{`@keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}`}</style>
              </div>
            )}

            {/* Resolved banner */}
            {isResolved && (
              <div style={{ textAlign: "center", padding: "12px 16px", background: "#f0fdf4", borderRadius: 10, border: "1px solid #bbf7d0", color: "#166534", fontSize: 13 }}>
                ✓ Conversation resolved —{" "}
                <button onClick={resetChat} style={{ background: "none", border: "none", color: "#16a34a", fontWeight: 600, cursor: "pointer", fontFamily: "inherit", fontSize: 13 }}>
                  Start new test
                </button>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input */}
          {!isResolved && (
            <div style={{ padding: 12, borderTop: "1px solid var(--slate-100)", display: "flex", gap: 8 }}>
              <input className="input" value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                placeholder="Type a message…"
                disabled={wsStatus !== "connected"}
                style={{ flex: 1 }} />
              <button className="btn btn-primary" onClick={() => sendMessage()}
                disabled={wsStatus !== "connected" || !input.trim()}>
                Send
              </button>
            </div>
          )}
        </div>

        {/* Debug panel */}
        {showDebug && (
          <div style={{ width: 380, background: "var(--slate-900)", borderRadius: 12, border: "1px solid #334155", display: "flex", flexDirection: "column", overflow: "hidden" }}>
            <div style={{ padding: "14px 20px", borderBottom: "1px solid #334155", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <p style={{ color: "#94a3b8", fontSize: 13, fontWeight: 600, margin: 0 }}>WS Event Log</p>
              <button onClick={() => setDebugLog([])} style={{ fontSize: 11, background: "none", border: "1px solid #475569", color: "#94a3b8", borderRadius: 4, padding: "2px 8px", cursor: "pointer", fontFamily: "inherit" }}>Clear</button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 12, display: "flex", flexDirection: "column", gap: 8 }}>
              {debugLog.length === 0 ? (
                <p style={{ color: "#475569", fontSize: 13 }}>WS events appear here. Click ⚙ Debug on a message too.</p>
              ) : debugLog.slice().reverse().map((evt, i) => (
                <div key={i} style={{ borderRadius: 6, background: "#1e293b", padding: "8px 10px" }}>
                  <span style={{ fontSize: 10, color: "#64748b", display: "block", marginBottom: 4 }}>
                    {evt.ts ? evt.ts.slice(11, 23) : ""} — <strong style={{ color: (evt.type === "message" ? "#4ade80" : evt.type === "ai_thinking" ? "#fbbf24" : "#94a3b8") }}>{evt.type}</strong>
                  </span>
                  <pre style={{ color: "#a5f3fc", fontSize: 11, margin: 0, whiteSpace: "pre-wrap", wordBreak: "break-all" }}>
                    {JSON.stringify(evt, null, 2)}
                  </pre>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================================= */
/* Staff Management Tab                                                            */
/* ============================================================================= */
function AdminStaffTab() {
  const [staff, setStaff] = useState<any[]>([]);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [disabling, setDisabling] = useState<string | null>(null);

  const loadStaff = () => {
    apiFetch("/api/v1/admin/staff")
      .then((d) => setStaff(d.staff || []))
      .catch(console.error);
  };

  useEffect(() => { loadStaff(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreating(true);
    setError("");
    setSuccess("");
    try {
      await apiFetch("/api/v1/admin/staff", {
        method: "POST",
        body: JSON.stringify(form),
      });
      setSuccess(`Staff member ${form.email} created successfully.`);
      setForm({ name: "", email: "", password: "" });
      loadStaff();
    } catch (err: any) { setError(err.message || "Failed to create staff"); }
    setCreating(false);
  };

  const disableStaff = async (userId: string) => {
    if (!confirm("Disable this staff member? They will no longer be able to log in.")) return;
    setDisabling(userId);
    try {
      await apiFetch(`/api/v1/admin/staff/${userId}`, { method: "DELETE" });
      loadStaff();
    } catch (err) { console.error(err); }
    setDisabling(null);
  };

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Staff Management</h1>
      <p style={{ fontSize: 14, color: "var(--slate-500)", marginBottom: 28 }}>
        Add and manage staff members for your company.
      </p>

      <div className="card" style={{ marginBottom: 24 }}>
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Add Staff Member</h3>
        {error && (
          <div style={{ background: "#fef2f2", color: "#dc2626", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 14, border: "1px solid #fecaca" }}>
            {error}
          </div>
        )}
        {success && (
          <div style={{ background: "#dcfce7", color: "#166534", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 14 }}>
            ✅ {success}
          </div>
        )}
        <form onSubmit={handleCreate} style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr auto", gap: 12, alignItems: "end" }}>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--slate-600)", marginBottom: 5 }}>Full Name</label>
            <input className="input" placeholder="Jane Smith" value={form.name}
              onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))} required />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--slate-600)", marginBottom: 5 }}>Email</label>
            <input type="email" className="input" placeholder="jane@company.com" value={form.email}
              onChange={(e) => setForm((p) => ({ ...p, email: e.target.value }))} required />
          </div>
          <div>
            <label style={{ display: "block", fontSize: 12, fontWeight: 500, color: "var(--slate-600)", marginBottom: 5 }}>Password</label>
            <input type="password" className="input" placeholder="••••••••" value={form.password} minLength={8}
              onChange={(e) => setForm((p) => ({ ...p, password: e.target.value }))} required />
          </div>
          <button className="btn btn-primary" type="submit" disabled={creating} style={{ padding: "10px 18px", fontSize: 13 }}>
            {creating ? "Adding..." : "Add Staff"}
          </button>
        </form>
      </div>

      <div className="card">
        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16 }}>Staff Members ({staff.length})</h3>
        {staff.length === 0 ? (
          <p style={{ color: "var(--slate-400)", fontSize: 14 }}>No staff members yet.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {staff.map((s: any) => (
              <div key={s.user_id || s._id} style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                padding: "12px 16px", background: "var(--slate-50)", borderRadius: 8,
              }}>
                <div>
                  <p style={{ fontWeight: 500, fontSize: 14, marginBottom: 2 }}>{s.name || s.email}</p>
                  <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
                    {s.email} · {new Date(s.created_at).toLocaleDateString()}
                  </p>
                </div>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  {s.enabled === false ? (
                    <span style={{ fontSize: 11, padding: "3px 9px", borderRadius: 4, background: "#fee2e2", color: "#991b1b", fontWeight: 600 }}>
                      disabled
                    </span>
                  ) : (
                    <button
                      onClick={() => disableStaff(s.user_id || s._id)}
                      disabled={disabling === (s.user_id || s._id)}
                      style={{
                        padding: "5px 12px", borderRadius: 6, border: "1px solid #fecaca",
                        background: "white", color: "#ef4444", fontSize: 12,
                        cursor: "pointer", fontFamily: "inherit",
                      }}
                    >
                      {disabling === (s.user_id || s._id) ? "..." : "Disable"}
                    </button>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ============================================================================= */
/* Company Settings Tab                                                            */
/* ============================================================================= */
function AdminSettingsTab() {
  const [settings, setSettings] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    apiFetch("/api/v1/admin/settings")
      .then((d) => setSettings(d.settings || d))
      .catch(console.error);
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    try {
      await apiFetch("/api/v1/admin/settings", {
        method: "PATCH",
        body: JSON.stringify(settings),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
    } catch (err) { console.error(err); }
    setSaving(false);
  };

  if (!settings) return <p style={{ color: "var(--slate-400)" }}>Loading settings...</p>;

  return (
    <div>
      <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 6 }}>Company Settings</h1>
      <p style={{ fontSize: 14, color: "var(--slate-500)", marginBottom: 28 }}>
        Configure AI behavior thresholds and automation flags.
      </p>

      <div className="card" style={{ maxWidth: 560 }}>
        {saved && (
          <div style={{ background: "#dcfce7", color: "#166534", padding: "10px 14px", borderRadius: 8, fontSize: 13, marginBottom: 20 }}>
            ✅ Settings saved successfully.
          </div>
        )}

        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--slate-700)", marginBottom: 6 }}>
            Auto-Resolve Threshold
            <span style={{ fontSize: 12, fontWeight: 400, color: "var(--slate-400)", marginLeft: 8 }}>
              (current: {((settings.auto_resolve_threshold || 0.82) * 100).toFixed(0)}%)
            </span>
          </label>
          <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 8 }}>
            AI responses above this confidence threshold are sent automatically.
          </p>
          <input type="range" min="0.5" max="0.99" step="0.01"
            value={settings.auto_resolve_threshold || 0.82}
            onChange={(e) => setSettings((p: any) => ({ ...p, auto_resolve_threshold: parseFloat(e.target.value) }))}
            style={{ width: "100%", marginBottom: 4 }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--slate-400)" }}>
            <span>50% (more auto)</span><span>99% (less auto)</span>
          </div>
        </div>

        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: "var(--slate-700)", marginBottom: 6 }}>
            Clarify Threshold
            <span style={{ fontSize: 12, fontWeight: 400, color: "var(--slate-400)", marginLeft: 8 }}>
              (current: {((settings.clarify_threshold || 0.60) * 100).toFixed(0)}%)
            </span>
          </label>
          <p style={{ fontSize: 12, color: "var(--slate-400)", marginBottom: 8 }}>
            Below auto-resolve but above this → AI asks clarifying question. Below this → escalate.
          </p>
          <input type="range" min="0.3" max="0.9" step="0.01"
            value={settings.clarify_threshold || 0.60}
            onChange={(e) => setSettings((p: any) => ({ ...p, clarify_threshold: parseFloat(e.target.value) }))}
            style={{ width: "100%", marginBottom: 4 }} />
          <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--slate-400)" }}>
            <span>30%</span><span>90%</span>
          </div>
        </div>

        <div style={{ marginBottom: 28 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}>
            <input type="checkbox"
              checked={settings.auto_resolve_auto_close !== false}
              onChange={(e) => setSettings((p: any) => ({ ...p, auto_resolve_auto_close: e.target.checked }))}
              style={{ width: 16, height: 16 }} />
            <div>
              <p style={{ fontSize: 13, fontWeight: 600, color: "var(--slate-700)", marginBottom: 2 }}>Auto-close on AI resolution</p>
              <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
                When enabled, AI-resolved conversations are automatically marked as resolved.
              </p>
            </div>
          </label>
        </div>

        <button className="btn btn-primary" onClick={handleSave} disabled={saving} style={{ padding: "11px 24px", fontSize: 14 }}>
          {saving ? "Saving..." : "Save Settings"}
        </button>
      </div>
    </div>
  );
}

/* ============================================================================= */
/* KB Entries Tab                                                                  */
/* ============================================================================= */
function AdminKBEntriesTab() {
  const [entries, setEntries] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [editing, setEditing] = useState<any | null>(null);
  const [editForm, setEditForm] = useState({ canonical_answer: "", title: "", tags: "", verified: true });
  const [saving, setSaving] = useState(false);

  const loadEntries = () => {
    setLoading(true);
    apiFetch("/api/v1/admin/kb-entries")
      .then((d) => setEntries(d.kb_entries || []))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { loadEntries(); }, []);

  const deleteEntry = async (entryId: string) => {
    if (!confirm("Delete this KB entry and remove it from the vector index?")) return;
    setDeleting(entryId);
    try {
      await apiFetch(`/api/v1/admin/kb-entries/${entryId}`, { method: "DELETE" });
      loadEntries();
    } catch (err) { console.error(err); }
    setDeleting(null);
  };

  const openEdit = (entry: any) => {
    setEditing(entry);
    setEditForm({
      canonical_answer: entry.canonical_answer || "",
      title: entry.title || "",
      tags: entry.tags || "",
      verified: entry.verified !== false,
    });
  };

  const saveEdit = async () => {
    if (!editing) return;
    setSaving(true);
    try {
      await apiFetch(`/api/v1/admin/kb-entries/${editing._id || editing.entry_id}`, {
        method: "PATCH",
        body: JSON.stringify(editForm),
      });
      setEditing(null);
      loadEntries();
    } catch (err) { console.error(err); }
    setSaving(false);
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>KB Entries</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>
            Verified Q&A pairs from resolved conversations — embedded in the vector index.
          </p>
        </div>
      </div>

      {loading ? (
        <p style={{ color: "var(--slate-400)" }}>Loading...</p>
      ) : entries.length === 0 ? (
        <div className="card" style={{ textAlign: "center", padding: 48 }}>
          <p style={{ fontSize: 28, marginBottom: 8 }}>🧠</p>
          <p style={{ color: "var(--slate-500)", fontSize: 14 }}>No KB entries yet. Resolve a conversation to create one.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {entries.map((entry: any) => (
            <div key={entry._id || entry.entry_id} className="card" style={{ padding: "16px 20px" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                <div style={{ flex: 1, marginRight: 16, minWidth: 0 }}>
                  <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
                    <p style={{ fontWeight: 600, fontSize: 14 }}>{entry.title}</p>
                    <span style={{
                      fontSize: 10, padding: "2px 8px", borderRadius: 4, fontWeight: 600,
                      background: entry.verified ? "#dcfce7" : "#fef3c7",
                      color: entry.verified ? "#166534" : "#92400e",
                    }}>
                      {entry.verified ? "Verified" : "Unverified"}
                    </span>
                  </div>
                  <p style={{ fontSize: 13, color: "var(--slate-600)", lineHeight: 1.5, marginBottom: 8 }}>
                    {entry.canonical_answer?.substring(0, 200)}{entry.canonical_answer?.length > 200 ? "..." : ""}
                  </p>
                  <p style={{ fontSize: 11, color: "var(--slate-400)" }}>
                    {entry.source_type}
                    {entry.tags ? ` · ${entry.tags}` : ""}
                    {entry.created_at ? ` · ${new Date(entry.created_at).toLocaleDateString()}` : ""}
                    {entry.endee_doc_id ? " · indexed in vector DB" : ""}
                  </p>
                </div>
                <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                  <button onClick={() => openEdit(entry)} style={{
                    padding: "5px 12px", borderRadius: 6, border: "1px solid var(--slate-200)",
                    background: "white", color: "var(--slate-600)", fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                  }}>Edit</button>
                  <button
                    onClick={() => deleteEntry(entry._id || entry.entry_id)}
                    disabled={deleting === (entry._id || entry.entry_id)}
                    style={{
                      padding: "5px 12px", borderRadius: 6, border: "1px solid #fecaca",
                      background: "white", color: "#ef4444", fontSize: 12, cursor: "pointer", fontFamily: "inherit",
                    }}
                  >
                    {deleting === (entry._id || entry.entry_id) ? "..." : "Delete"}
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {editing && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 100, padding: 24,
        }}>
          <div className="card" style={{ width: 520, padding: 32 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 20 }}>Edit KB Entry</h2>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>Title</label>
              <input className="input" value={editForm.title}
                onChange={(e) => setEditForm((p) => ({ ...p, title: e.target.value }))} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>Canonical Answer</label>
              <textarea className="input" rows={5} value={editForm.canonical_answer}
                onChange={(e) => setEditForm((p) => ({ ...p, canonical_answer: e.target.value }))}
                style={{ resize: "vertical", fontFamily: "inherit" }} />
            </div>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>Tags</label>
              <input className="input" value={editForm.tags}
                onChange={(e) => setEditForm((p) => ({ ...p, tags: e.target.value }))}
                placeholder="billing, account, password" />
            </div>
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
                <input type="checkbox" checked={editForm.verified}
                  onChange={(e) => setEditForm((p) => ({ ...p, verified: e.target.checked }))}
                  style={{ width: 14, height: 14 }} />
                <span style={{ fontSize: 13, color: "var(--slate-700)" }}>Verified</span>
              </label>
            </div>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setEditing(null)} style={{
                padding: "10px 20px", borderRadius: 8, border: "1px solid var(--slate-200)",
                background: "white", color: "var(--slate-600)", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              }}>Cancel</button>
              <button className="btn btn-primary" onClick={saveEdit} disabled={saving} style={{ padding: "10px 20px", fontSize: 13 }}>
                {saving ? "Saving..." : "Save Changes"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================================= */
/* Conversations Tab — widget conversations managed by Admin                     */
/* ============================================================================= */
function AdminConversationsTab() {
  const [convs, setConvs] = useState<any[]>([]);
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "resolved">("active");
  const [selected, setSelected] = useState<any>(null);
  const [messages, setMessages] = useState<any[]>([]);
  const [reply, setReply] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(false);
  const [resolveOpen, setResolveOpen] = useState(false);
  const [canonicalAnswer, setCanonicalAnswer] = useState("");
  const [resolveTitle, setResolveTitle] = useState("");
  const [resolveTags, setResolveTags] = useState("");
  const [resolving, setResolving] = useState(false);
  const [resolveMsg, setResolveMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadConvs = async () => {
    const qs = statusFilter ? `?status=${statusFilter}` : "";
    try {
      const d = await apiFetch(`/api/v1/conversations${qs}`);
      setConvs(d.conversations || []);
    } catch (e: any) { setErr(e.message); }
  };

  const loadMessages = async (conv: any) => {
    setLoading(true);
    setSelected(conv);
    setMessages([]);
    setReply("");
    setResolveMsg(null);
    try {
      const d = await apiFetch(`/api/v1/conversations/${conv.conv_id}`);
      setMessages(d.messages || []);
    } catch (e: any) { setErr(e.message); }
    setLoading(false);
  };

  useEffect(() => { loadConvs(); }, [statusFilter]);

  // Auto-refresh every 12s
  useEffect(() => {
    const t = setInterval(() => {
      loadConvs();
      if (selected) loadMessages(selected);
    }, 12000);
    return () => clearInterval(t);
  }, [statusFilter, selected]);

  const sendReply = async () => {
    if (!reply.trim() || !selected) return;
    setSending(true);
    try {
      await apiFetch(`/api/v1/conversations/${selected.conv_id}/message`, {
        method: "POST",
        body: JSON.stringify({ content: reply.trim() }),
      });
      setReply("");
      await loadMessages(selected);
    } catch (e: any) { setErr(e.message); }
    setSending(false);
  };

  const openResolve = () => {
    const lastAI = [...messages].reverse().find((m) => m.sender_type === "ai");
    const isEscalation = !lastAI || lastAI?.metadata?.action === "escalate";
    setCanonicalAnswer(isEscalation ? "" : (lastAI?.content || ""));
    setResolveTitle("");
    setResolveTags("");
    setResolveMsg(null);
    setResolveOpen(true);
  };

  const submitResolve = async () => {
    if (!canonicalAnswer.trim() || !selected) return;
    setResolving(true);
    setResolveMsg(null);
    try {
      const data = await apiFetch(`/api/v1/conversations/${selected.conv_id}/resolve`, {
        method: "POST",
        body: JSON.stringify({
          canonical_answer: canonicalAnswer.trim(),
          title: resolveTitle.trim(),
          tags: resolveTags.trim(),
          ingest_to_kb: true,
        }),
      });
      setResolveMsg(`✅ Resolved & ingested — ${data.chunks_ingested ?? 0} chunks embedded into KB`);
      setTimeout(() => {
        setResolveOpen(false);
        setResolveMsg(null);
        setSelected(null);
        loadConvs();
      }, 2000);
    } catch (e: any) {
      setResolveMsg(`error:${e.message}`);
    }
    setResolving(false);
  };

  const statusBadge = (s: string) => {
    const styles: Record<string, { bg: string; color: string }> = {
      active:   { bg: "#dbeafe", color: "#1e40af" },
      resolved: { bg: "#dcfce7", color: "#166534" },
      archived: { bg: "#f1f5f9", color: "#475569" },
    };
    const st = styles[s] || styles.archived;
    return (
      <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 4, fontWeight: 600, background: st.bg, color: st.color }}>
        {s}
      </span>
    );
  };

  const senderStyle = (type: string) => {
    if (type === "customer") return { bg: "#f1f5f9", align: "flex-start" as const, textAlign: "left" as const };
    if (type === "ai")       return { bg: "#ede9fe", align: "flex-start" as const, textAlign: "left" as const };
    return                         { bg: "#dcfce7", align: "flex-end"   as const, textAlign: "right" as const };
  };

  const fmtTime = (ts: string) => {
    if (!ts) return "";
    return new Date(ts).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, marginBottom: 4 }}>Conversations</h1>
          <p style={{ fontSize: 14, color: "var(--slate-500)" }}>{convs.length} conversation{convs.length !== 1 ? "s" : ""}</p>
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          {(["active", "", "resolved"] as const).map((s) => (
            <button key={s} onClick={() => { setStatusFilter(s); setSelected(null); }} style={{
              padding: "6px 14px", borderRadius: 6, border: "none", cursor: "pointer",
              background: statusFilter === s ? "#3b82f6" : "#e2e8f0",
              color: statusFilter === s ? "white" : "#475569",
              fontSize: 13, fontFamily: "inherit", fontWeight: 600,
            }}>
              {s === "" ? "All" : s.charAt(0).toUpperCase() + s.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {err && (
        <div style={{ padding: "10px 16px", background: "#fee2e2", color: "#991b1b", borderRadius: 8, marginBottom: 16, fontSize: 13 }}>
          {err} <button onClick={() => setErr(null)} style={{ border: "none", background: "none", cursor: "pointer", marginLeft: 8 }}>✕</button>
        </div>
      )}

      <div style={{ display: "flex", gap: 20, alignItems: "flex-start" }}>
        {/* ---- Conversation list ---- */}
        <div style={{ width: 300, flexShrink: 0 }}>
          {convs.length === 0 ? (
            <div className="card" style={{ textAlign: "center", padding: 32, color: "var(--slate-400)" }}>
              No conversations found
            </div>
          ) : (
            convs.map((c) => (
              <div key={c.conv_id} onClick={() => loadMessages(c)} className="card" style={{
                marginBottom: 10, cursor: "pointer", padding: "14px 16px",
                border: selected?.conv_id === c.conv_id ? "2px solid #3b82f6" : "2px solid transparent",
                transition: "border 0.15s",
              }}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 6 }}>
                  {statusBadge(c.status)}
                  <span style={{ fontFamily: "monospace", fontSize: 11, color: "#94a3b8" }}>#{(c.conv_id || "").slice(-8)}</span>
                </div>
                <p style={{ fontSize: 13, fontWeight: 600, margin: "0 0 3px", color: "var(--slate-800)" }}>
                  {c.customer_id ? `${c.customer_id.slice(0, 20)}…` : "Widget Customer"}
                </p>
                {c.assigned_staff_id && (
                  <p style={{ fontSize: 11, color: "#64748b", margin: 0 }}>Assigned: {c.assigned_staff_id.slice(0, 16)}…</p>
                )}
                <p style={{ fontSize: 11, color: "#94a3b8", margin: "4px 0 0" }}>{fmtTime(c.created_at)}</p>
              </div>
            ))
          )}
        </div>

        {/* ---- Message thread ---- */}
        {selected ? (
          <div className="card" style={{ flex: 1, padding: 0, overflow: "hidden" }}>
            {/* Header */}
            <div style={{ padding: "14px 20px", borderBottom: "1px solid var(--slate-100)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
              <div>
                <span style={{ fontWeight: 700, fontSize: 15 }}>
                  Conv <span style={{ fontFamily: "monospace", fontWeight: 400, fontSize: 13 }}>#{selected.conv_id.slice(-8)}</span>
                </span>
                <span style={{ marginLeft: 12 }}>{statusBadge(selected.status)}</span>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                {selected.status === "active" && (
                  <button onClick={openResolve} style={{
                    padding: "6px 14px", borderRadius: 6, border: "none",
                    background: "#22c55e", color: "white", fontSize: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
                  }}>Resolve & Ingest</button>
                )}
                <button onClick={() => setSelected(null)} style={{
                  padding: "6px 12px", borderRadius: 6, border: "1px solid var(--slate-200)",
                  background: "white", color: "var(--slate-600)", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
                }}>✕</button>
              </div>
            </div>

            {/* Messages */}
            <div style={{ padding: 20, maxHeight: 420, overflowY: "auto", display: "flex", flexDirection: "column", gap: 12 }}>
              {loading ? (
                <p style={{ color: "var(--slate-400)", textAlign: "center" }}>Loading…</p>
              ) : messages.length === 0 ? (
                <p style={{ color: "var(--slate-400)", textAlign: "center" }}>No messages yet</p>
              ) : (
                messages.map((m) => {
                  const s = senderStyle(m.sender_type);
                  return (
                    <div key={m.msg_id} style={{ display: "flex", flexDirection: "column", alignItems: s.align }}>
                      <div style={{ maxWidth: "72%", background: s.bg, borderRadius: 10, padding: "8px 12px" }}>
                        <p style={{ fontSize: 11, color: "#94a3b8", marginBottom: 3, textAlign: s.textAlign }}>
                          {m.sender_type === "ai" ? "🤖 AI" : m.sender_type === "customer" ? "👤 Customer" : "👤 Staff"} · {fmtTime(m.created_at)}
                        </p>
                        <p style={{ fontSize: 14, margin: 0, color: "var(--slate-800)", whiteSpace: "pre-wrap" }}>{m.content}</p>
                        {m.metadata?.action && (
                          <p style={{ fontSize: 11, marginTop: 4, color: "#64748b" }}>
                            {m.metadata.action}{m.metadata.confidence != null ? ` · ${Math.round(m.metadata.confidence * 100)}%` : ""}
                          </p>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Reply box */}
            {selected.status === "active" && (
              <div style={{ padding: "14px 20px", borderTop: "1px solid var(--slate-100)", display: "flex", gap: 10 }}>
                <input className="input" value={reply}
                  onChange={(e) => setReply(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendReply(); } }}
                  placeholder="Type reply… (Enter to send)"
                  style={{ flex: 1, fontSize: 14 }} disabled={sending} />
                <button onClick={sendReply} disabled={!reply.trim() || sending} style={{
                  padding: "10px 20px", borderRadius: 8, border: "none",
                  background: "#3b82f6", color: "white", fontSize: 14,
                  cursor: reply.trim() && !sending ? "pointer" : "not-allowed",
                  opacity: reply.trim() && !sending ? 1 : 0.5, fontFamily: "inherit",
                }}>{sending ? "…" : "Send"}</button>
              </div>
            )}
          </div>
        ) : (
          <div className="card" style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", minHeight: 300, color: "var(--slate-400)" }}>
            Select a conversation to view messages
          </div>
        )}
      </div>

      {/* ---- Resolve Modal ---- */}
      {resolveOpen && (
        <div style={{
          position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)",
          display: "flex", alignItems: "center", justifyContent: "center", zIndex: 200, padding: 24,
        }}>
          <div className="card" style={{ width: 540, padding: 32 }}>
            <h2 style={{ fontSize: 18, fontWeight: 700, marginBottom: 6 }}>Resolve & Ingest</h2>
            <p style={{ fontSize: 13, color: "var(--slate-500)", marginBottom: 20 }}>
              This answer will be embedded into the vector store. The AI will use it to auto-resolve similar questions.
            </p>
            {!canonicalAnswer && (
              <div style={{ padding: "10px 14px", background: "#fef3c7", borderRadius: 8, marginBottom: 16, fontSize: 13, color: "#92400e" }}>
                ⚠️ The AI escalated this conversation. Write the correct answer below — it will be learned by the KB.
              </div>
            )}
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Canonical Answer *</label>
              <textarea className="input" rows={5} value={canonicalAnswer}
                onChange={(e) => setCanonicalAnswer(e.target.value)}
                placeholder="Write the definitive, correct answer…"
                style={{ resize: "vertical", fontFamily: "inherit" }} />
            </div>
            <div style={{ marginBottom: 14 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Title (optional)</label>
              <input className="input" value={resolveTitle} onChange={(e) => setResolveTitle(e.target.value)} placeholder="Auto-generated if blank" />
            </div>
            <div style={{ marginBottom: 20 }}>
              <label style={{ display: "block", fontSize: 13, fontWeight: 500, marginBottom: 6 }}>Tags (optional)</label>
              <input className="input" value={resolveTags} onChange={(e) => setResolveTags(e.target.value)} placeholder="billing, orders" />
            </div>
            {resolveMsg && (
              <div style={{
                padding: "10px 14px", borderRadius: 8, marginBottom: 16, fontSize: 13,
                background: resolveMsg.startsWith("error:") ? "#fee2e2" : "#dcfce7",
                color: resolveMsg.startsWith("error:") ? "#991b1b" : "#166534",
              }}>{resolveMsg.replace(/^error:/, "")}</div>
            )}
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
              <button onClick={() => setResolveOpen(false)} style={{
                padding: "10px 20px", borderRadius: 8, border: "1px solid var(--slate-200)",
                background: "white", color: "var(--slate-600)", fontSize: 13, cursor: "pointer", fontFamily: "inherit",
              }}>Cancel</button>
              <button onClick={submitResolve} disabled={!canonicalAnswer.trim() || resolving} style={{
                padding: "10px 20px", borderRadius: 8, border: "none",
                background: "#22c55e", color: "white", fontSize: 13, fontFamily: "inherit", fontWeight: 600,
                cursor: canonicalAnswer.trim() && !resolving ? "pointer" : "not-allowed",
                opacity: canonicalAnswer.trim() && !resolving ? 1 : 0.5,
              }}>{resolving ? "Resolving…" : "Resolve & Ingest"}</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
