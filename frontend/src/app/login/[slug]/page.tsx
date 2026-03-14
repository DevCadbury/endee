"use client";

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";

/* =============================================================================
   /login/[slug] — Company-specific login page
   Fetches company name from API, shows branded login form,
   routes by role after successful login.
   ============================================================================= */

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SlugLoginPage() {
  const router = useRouter();
  const params = useParams();
  const slug = params?.slug as string;

  const [companyName, setCompanyName] = useState<string | null>(null);
  const [companyId, setCompanyId] = useState("");
  const [loadingCompany, setLoadingCompany] = useState(true);
  const [notFound, setNotFound] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Fetch company info from slug
  useEffect(() => {
    if (!slug) return;
    fetch(`${API_URL}/api/v1/auth/company/${slug}`)
      .then((r) => {
        if (!r.ok) throw new Error("not found");
        return r.json();
      })
      .then((d) => {
        setCompanyName(d.name);
        setCompanyId(d.company_id || "");
        setLoadingCompany(false);
      })
      .catch(() => {
        setNotFound(true);
        setLoadingCompany(false);
      });
  }, [slug]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch(`${API_URL}/api/v1/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || "Login failed");
      }

      const data = await res.json();
      localStorage.setItem("token", data.token);
      localStorage.setItem("company_id", data.company_id);
      localStorage.setItem("email", data.email);
      localStorage.setItem("role", data.role || "admin");
      localStorage.setItem("user_id", data.user_id || "");
      localStorage.setItem("slug", slug);

      // Route based on role
      const role = data.role || "admin";
      if (role === "superadmin") router.push("/superadmin");
      else if (role === "staff") router.push("/staff");
      else router.push("/dashboard");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Loading state
  if (loadingCompany) {
    return (
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", background: "var(--slate-50)",
      }}>
        <p style={{ color: "var(--slate-400)", fontSize: 14 }}>Loading...</p>
      </div>
    );
  }

  // Not found
  if (notFound) {
    return (
      <div style={{
        minHeight: "100vh", display: "flex", alignItems: "center",
        justifyContent: "center", background: "var(--slate-50)", padding: 24,
      }}>
        <div className="card animate-fade-in-up" style={{ width: 400, padding: 36, textAlign: "center" }}>
          <p style={{ fontSize: 40, marginBottom: 16 }}>🔍</p>
          <h1 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8 }}>Company not found</h1>
          <p style={{ color: "var(--slate-500)", fontSize: 14, marginBottom: 24 }}>
            No company with slug <strong>{slug}</strong> exists.
          </p>
          <a href="/login" className="btn btn-primary" style={{ display: "inline-block" }}>
            Try another slug
          </a>
        </div>
      </div>
    );
  }

  return (
    <div style={{
      minHeight: "100vh",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      background: "var(--slate-50)",
      padding: 24,
    }}>
      <div className="card animate-fade-in-up" style={{ width: 400, padding: 36 }}>
        {/* Logo + company branding */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 8,
          justifyContent: "center",
        }}>
          <div style={{
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
          }}>
            R
          </div>
          <span style={{ fontWeight: 700, fontSize: 22, color: "var(--slate-900)" }}>
            ResolveAI
          </span>
        </div>

        {/* Company name chip */}
        <div style={{ textAlign: "center", marginBottom: 28 }}>
          <span style={{
            display: "inline-block",
            padding: "4px 12px",
            borderRadius: 20,
            background: "var(--primary-50)",
            color: "var(--primary-dark)",
            fontSize: 12,
            fontWeight: 600,
            marginBottom: 16,
          }}>
            {companyName}
          </span>
          <h1 style={{ fontSize: 22, fontWeight: 700, marginBottom: 6 }}>
            Welcome back
          </h1>
          <p style={{ color: "var(--slate-500)", fontSize: 14 }}>
            Sign in to your team account
          </p>
        </div>

        {error && (
          <div style={{
            background: "#fef2f2",
            color: "#dc2626",
            padding: "10px 14px",
            borderRadius: 8,
            fontSize: 13,
            marginBottom: 16,
            border: "1px solid #fecaca",
          }}>
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{
              display: "block",
              fontSize: 13,
              fontWeight: 500,
              color: "var(--slate-700)",
              marginBottom: 6,
            }}>
              Email
            </label>
            <input
              type="email"
              className="input"
              placeholder="you@company.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label style={{
              display: "block",
              fontSize: 13,
              fontWeight: 500,
              color: "var(--slate-700)",
              marginBottom: 6,
            }}>
              Password
            </label>
            <input
              type="password"
              className="input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
            />
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            disabled={loading}
            style={{ width: "100%", padding: "12px", fontSize: 14 }}
          >
            {loading ? "Signing in..." : "Sign In"}
          </button>
        </form>

        <p style={{
          textAlign: "center",
          marginTop: 16,
          fontSize: 12,
          color: "var(--slate-400)",
        }}>
          Not your company?{" "}
          <a href="/login" style={{ color: "var(--slate-500)", fontWeight: 500 }}>
            Switch team
          </a>
        </p>
      </div>
    </div>
  );
}
