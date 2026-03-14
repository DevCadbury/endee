"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   Register Page — Company signup with admin user creation
   After success: shows company slug + unique login URL
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function RegisterPage() {
  const router = useRouter();
  const [form, setForm] = useState({
    company_name: "",
    email: "",
    password: "",
    domain: "",
  });
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState<{
    slug: string;
    login_url: string;
    email: string;
  } | null>(null);
  const [copied, setCopied] = useState(false);

  const updateField = (field: string, value: string) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Registration failed");
      }

      const data = await res.json();
      localStorage.setItem("token", data.token);
      localStorage.setItem("company_id", data.company_id);
      localStorage.setItem("email", data.email);
      localStorage.setItem("role", data.role || "admin");
      localStorage.setItem("user_id", data.user_id || "");
      localStorage.setItem("slug", data.slug || "");

      setRegistered({
        slug: data.slug || "",
        login_url: data.login_url || `/login/${data.slug}`,
        email: data.email,
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const copyLoginUrl = () => {
    const fullUrl = `${window.location.origin}${registered!.login_url}`;
    navigator.clipboard.writeText(fullUrl).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  /* ---- Success Screen ---- */
  if (registered) {
    const fullUrl = `${typeof window !== "undefined" ? window.location.origin : ""}${registered.login_url}`;
    return (
      <div style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--slate-50)",
        padding: 24,
      }}>
        <div className="card animate-fade-in-up" style={{ width: 480, padding: 40, textAlign: "center" }}>
          <div style={{
            width: 56, height: 56, borderRadius: "50%",
            background: "#dcfce7", display: "flex",
            alignItems: "center", justifyContent: "center",
            margin: "0 auto 20px", fontSize: 28,
          }}>✓</div>

          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 8 }}>
            Company created!
          </h1>
          <p style={{ color: "var(--slate-500)", fontSize: 14, marginBottom: 28 }}>
            Your AI support platform is ready. Share your unique login URL with your team.
          </p>

          {/* Slug badge */}
          <div style={{
            background: "var(--slate-50)", border: "1px solid var(--slate-200)",
            borderRadius: 10, padding: "16px 20px", marginBottom: 16, textAlign: "left",
          }}>
            <p style={{ fontSize: 12, color: "var(--slate-400)", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: 4 }}>
              Company Slug
            </p>
            <p style={{ fontSize: 18, fontWeight: 700, color: "var(--slate-900)", fontFamily: "monospace" }}>
              {registered.slug}
            </p>
          </div>

          {/* Login URL */}
          <div style={{
            background: "#eff6ff", border: "1px solid #bfdbfe",
            borderRadius: 10, padding: "16px 20px", marginBottom: 20, textAlign: "left",
          }}>
            <p style={{ fontSize: 12, color: "#3b82f6", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>
              Your Team Login URL
            </p>
            <p style={{
              fontSize: 13, color: "#1e40af", fontFamily: "monospace",
              wordBreak: "break-all", marginBottom: 12,
            }}>
              {fullUrl}
            </p>
            <button
              onClick={copyLoginUrl}
              style={{
                padding: "8px 16px", borderRadius: 8,
                border: "1px solid #bfdbfe",
                background: copied ? "#dcfce7" : "white",
                color: copied ? "#166534" : "#3b82f6",
                fontSize: 13, cursor: "pointer", fontFamily: "inherit", fontWeight: 600,
                transition: "all 0.2s",
              }}
            >
              {copied ? "✓ Copied!" : "Copy Login URL"}
            </button>
          </div>

          <button
            className="btn btn-primary"
            onClick={() => router.push("/dashboard")}
            style={{ width: "100%", padding: 12, fontSize: 14, marginBottom: 12 }}
          >
            Go to Dashboard
          </button>
          <p style={{ fontSize: 12, color: "var(--slate-400)" }}>
            Logged in as {registered.email}
          </p>
        </div>
      </div>
    );
  }

  /* ---- Registration Form ---- */
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: "var(--slate-50)",
        padding: 24,
      }}
    >
      <div
        className="card animate-fade-in-up"
        style={{ width: 440, padding: 36 }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 32,
            justifyContent: "center",
          }}
        >
          <div
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              background: "var(--primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontWeight: 800,
              fontSize: 18,
            }}
          >
            R
          </div>
          <span style={{ fontWeight: 700, fontSize: 22, color: "var(--slate-900)" }}>
            ResolveAI
          </span>
        </div>

        <h1 style={{ fontSize: 22, textAlign: "center", marginBottom: 8, fontWeight: 700 }}>
          Create your account
        </h1>
        <p
          style={{
            textAlign: "center",
            color: "var(--slate-500)",
            fontSize: 14,
            marginBottom: 28,
          }}
        >
          Set up AI support for your company
        </p>

        {error && (
          <div
            style={{
              background: "#fef2f2",
              color: "#dc2626",
              padding: "10px 14px",
              borderRadius: 8,
              fontSize: 13,
              marginBottom: 16,
              border: "1px solid #fecaca",
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>
              Company Name
            </label>
            <input
              className="input"
              placeholder="Acme Corp"
              value={form.company_name}
              onChange={(e) => updateField("company_name", e.target.value)}
              required
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>
              Work Email
            </label>
            <input
              type="email"
              className="input"
              placeholder="you@acme.com"
              value={form.email}
              onChange={(e) => updateField("email", e.target.value)}
              required
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>
              Password
            </label>
            <input
              type="password"
              className="input"
              placeholder="••••••••"
              value={form.password}
              onChange={(e) => updateField("password", e.target.value)}
              required
              minLength={8}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "var(--slate-700)", marginBottom: 6 }}>
              Website (optional)
            </label>
            <input
              className="input"
              placeholder="https://acme.com"
              value={form.domain}
              onChange={(e) => updateField("domain", e.target.value)}
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: "100%", padding: "12px", fontSize: 14 }}
          >
            {loading ? "Creating account..." : "Create Account"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 20, fontSize: 13, color: "var(--slate-500)" }}>
          Already have an account?{" "}
          <a href="/login" style={{ fontWeight: 500 }}>Sign in</a>
        </p>
      </div>
    </div>
  );
}
