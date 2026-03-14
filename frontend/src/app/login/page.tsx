"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

/* =============================================================================
   Login Page — Redirect to company-specific login via slug
   ============================================================================= */

export default function LoginPage() {
  const router = useRouter();
  const [slug, setSlug] = useState(
    typeof window !== "undefined" ? localStorage.getItem("slug") || "" : ""
  );
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const s = slug.trim().toLowerCase();
    if (!s) { setError("Enter your company slug"); return; }
    router.push(`/login/${s}`);
  };

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
        style={{ width: 400, padding: 36 }}
      >
        {/* Logo */}
        <div style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          marginBottom: 32,
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

        <h1 style={{ fontSize: 22, textAlign: "center", marginBottom: 8, fontWeight: 700 }}>
          Sign in to your team
        </h1>
        <p style={{
          textAlign: "center",
          color: "var(--slate-500)",
          fontSize: 14,
          marginBottom: 28,
        }}>
          Enter your company slug to continue
        </p>

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
          <div style={{ marginBottom: 24 }}>
            <label style={{
              display: "block",
              fontSize: 13,
              fontWeight: 500,
              color: "var(--slate-700)",
              marginBottom: 6,
            }}>
              Company Slug
            </label>
            <div style={{ display: "flex", alignItems: "center", position: "relative" }}>
              <span style={{
                position: "absolute",
                left: 12,
                color: "var(--slate-400)",
                fontSize: 13,
                pointerEvents: "none",
              }}>
                resolveai.io/login/
              </span>
              <input
                className="input"
                placeholder="acme-corp"
                value={slug}
                onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                required
                style={{ paddingLeft: 128 }}
              />
            </div>
            <p style={{ fontSize: 12, color: "var(--slate-400)", marginTop: 6 }}>
              You received this when you registered. Check your dashboard for the login URL.
            </p>
          </div>

          <button
            type="submit"
            className="btn btn-primary"
            style={{ width: "100%", padding: "12px", fontSize: 14 }}
          >
            Continue
          </button>
        </form>

        <p style={{
          textAlign: "center",
          marginTop: 20,
          fontSize: 13,
          color: "var(--slate-500)",
        }}>
          Don&apos;t have an account?{" "}
          <a href="/register" style={{ fontWeight: 500 }}>Get started</a>
        </p>
      </div>
    </div>
  );
}
