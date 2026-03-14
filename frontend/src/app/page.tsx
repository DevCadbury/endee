"use client";

import { useState } from "react";

/* =============================================================================
   Landing Page — ResolveAI
   Stripe/Zendesk-inspired. Clean white, Forest Green primary, professional.
   ============================================================================= */

export default function LandingPage() {
  return (
    <div style={{ background: "var(--white)" }}>
      <Navbar />
      <Hero />
      <Features />
      <HowItWorks />
      <LiveDemo />
      <CTA />
      <Footer />
    </div>
  );
}

/* ---------- Navbar ---------- */
function Navbar() {
  return (
    <nav
      style={{
        position: "sticky",
        top: 0,
        zIndex: 100,
        background: "rgba(255,255,255,0.95)",
        backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--slate-100)",
        padding: "14px 0",
      }}
    >
      <div
        className="container-narrow"
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "10px" }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: 8,
              background: "var(--primary)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "white",
              fontWeight: 800,
              fontSize: 16,
            }}
          >
            R
          </div>
          <span
            style={{
              fontWeight: 700,
              fontSize: 20,
              color: "var(--slate-900)",
            }}
          >
            ResolveAI
          </span>
        </div>

        <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <a href="/login" className="btn btn-secondary" style={{ fontSize: 13 }}>
            Log In
          </a>
          <a href="/register" className="btn btn-primary" style={{ fontSize: 13 }}>
            Get Started Free
          </a>
        </div>
      </div>
    </nav>
  );
}

/* ---------- Hero ---------- */
function Hero() {
  return (
    <section
      style={{
        padding: "100px 0 80px",
        textAlign: "center",
        background: "linear-gradient(180deg, var(--primary-50) 0%, var(--white) 100%)",
      }}
    >
      <div className="container-narrow animate-fade-in-up">
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            background: "var(--primary-100)",
            color: "var(--primary-dark)",
            padding: "6px 16px",
            borderRadius: 99,
            fontSize: 13,
            fontWeight: 500,
            marginBottom: 24,
          }}
        >
          <span style={{ fontSize: 14 }}>✦</span> Powered by Endee Vector DB + OpenRouter
        </div>

        <h1
          style={{
            fontSize: "clamp(36px, 5vw, 60px)",
            lineHeight: 1.1,
            maxWidth: 800,
            margin: "0 auto 20px",
            fontWeight: 800,
          }}
        >
          Resolve Support Tickets{" "}
          <span style={{ color: "var(--primary)" }}>Before They Reach</span> Your Team
        </h1>

        <p
          style={{
            fontSize: 18,
            color: "var(--slate-500)",
            maxWidth: 580,
            margin: "0 auto 36px",
            lineHeight: 1.6,
          }}
        >
          AI that auto-resolves repeatable issues, escalates complex ones to humans, and continuously learns from every resolution. Multi-tenant, embeddable, and free to start.
        </p>

        <div style={{ display: "flex", gap: 14, justifyContent: "center" }}>
          <a
            href="/register"
            className="btn btn-primary"
            style={{ padding: "14px 32px", fontSize: 15 }}
          >
            Start Free →
          </a>
          <a
            href="#how-it-works"
            className="btn btn-secondary"
            style={{ padding: "14px 32px", fontSize: 15 }}
          >
            See How It Works
          </a>
        </div>
      </div>
    </section>
  );
}

/* ---------- Features ---------- */
const features = [
  {
    icon: "⚡",
    title: "Auto-Resolve",
    desc: "Instantly answers known questions using your KB. Cites sources for transparency.",
    color: "#16a34a",
  },
  {
    icon: "🧠",
    title: "Smart Escalation",
    desc: "Low confidence? It creates a ticket with full AI context so agents start informed.",
    color: "#3b82f6",
  },
  {
    icon: "🔄",
    title: "Learning Loop",
    desc: "Every resolved ticket is automatically indexed back into your KB for future matches.",
    color: "#f59e0b",
  },
  {
    icon: "📚",
    title: "Multi-Source KB",
    desc: "Ingest from Slack, PDFs, email, Confluence, Notion, and past tickets.",
    color: "#8b5cf6",
  },
  {
    icon: "🔐",
    title: "Multi-Tenant",
    desc: "Each company's data is fully isolated. Endee metadata filters ensure zero bleed.",
    color: "#ef4444",
  },
  {
    icon: "📊",
    title: "Full Audit Trail",
    desc: "Every AI decision is logged with provenance, confidence scores, and latency.",
    color: "#06b6d4",
  },
];

function Features() {
  return (
    <section style={{ padding: "80px 0" }}>
      <div className="container-narrow">
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <h2 style={{ fontSize: 32, marginBottom: 12 }}>
            Everything You Need for AI Support
          </h2>
          <p style={{ color: "var(--slate-500)", fontSize: 16, maxWidth: 500, margin: "0 auto" }}>
            Built on proven RAG patterns with production-grade reliability.
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))",
            gap: 20,
          }}
        >
          {features.map((f, i) => (
            <div
              key={i}
              className="card"
              style={{ cursor: "default" }}
            >
              <div
                style={{
                  width: 44,
                  height: 44,
                  borderRadius: 10,
                  background: f.color + "12",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 22,
                  marginBottom: 16,
                }}
              >
                {f.icon}
              </div>
              <h3 style={{ fontSize: 17, marginBottom: 8, fontWeight: 600 }}>
                {f.title}
              </h3>
              <p style={{ color: "var(--slate-500)", fontSize: 14, lineHeight: 1.5 }}>
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------- How It Works ---------- */
const steps = [
  {
    num: "1",
    title: "Customer Sends Message",
    desc: "Your embedded widget sends the query to our backend via API. Rate-limited and authenticated.",
  },
  {
    num: "2",
    title: "Intent Classification",
    desc: "LLM quickly classifies intent: billing, technical, cancellation, or human request.",
  },
  {
    num: "3",
    title: "Vector Search",
    desc: "Message is embedded locally (bge-small) and searched against your KB in Endee with tenant isolation.",
  },
  {
    num: "4",
    title: "Decision Engine",
    desc: "Weighted scoring (similarity + intent + recency + reliability) triggers auto-reply, clarify, or escalate.",
  },
];

function HowItWorks() {
  return (
    <section
      id="how-it-works"
      style={{
        padding: "80px 0",
        background: "var(--slate-50)",
      }}
    >
      <div className="container-narrow">
        <div style={{ textAlign: "center", marginBottom: 56 }}>
          <h2 style={{ fontSize: 32, marginBottom: 12 }}>How It Works</h2>
          <p style={{ color: "var(--slate-500)", fontSize: 16 }}>
            From message to resolution in under 3.5 seconds.
          </p>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
            gap: 24,
          }}
        >
          {steps.map((s, i) => (
            <div key={i} style={{ textAlign: "center" }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: "50%",
                  background: "var(--primary)",
                  color: "white",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 18,
                  fontWeight: 700,
                  margin: "0 auto 16px",
                }}
              >
                {s.num}
              </div>
              <h3 style={{ fontSize: 16, marginBottom: 8, fontWeight: 600 }}>
                {s.title}
              </h3>
              <p
                style={{
                  color: "var(--slate-500)",
                  fontSize: 14,
                  lineHeight: 1.5,
                }}
              >
                {s.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ---------- Live Demo (Widget Preview) ---------- */
function LiveDemo() {
  const [messages, setMessages] = useState([
    { role: "bot", text: "👋 Hi! How can I help you today?" },
  ]);
  const [input, setInput] = useState("");

  const demoResponses: Record<string, { action: string; text: string }> = {
    invoice: {
      action: "auto_reply",
      text: 'Your latest invoice is available in Account → Billing → Invoices. You can download it as PDF. Source: [FAQ-042]',
    },
    refund: {
      action: "clarify",
      text: "Could you clarify — are you looking for a refund on a subscription charge or a one-time purchase?",
    },
    human: {
      action: "escalate",
      text: "I understand you'd like to speak with a human agent. Routing you now — an agent will be with you shortly.",
    },
  };

  const handleSend = () => {
    if (!input.trim()) return;
    const userMsg = input.trim().toLowerCase();
    setMessages((prev) => [...prev, { role: "user", text: input.trim() }]);
    setInput("");

    setTimeout(() => {
      let response = demoResponses["human"];
      if (userMsg.includes("invoice") || userMsg.includes("bill"))
        response = demoResponses["invoice"];
      else if (userMsg.includes("refund") || userMsg.includes("cancel"))
        response = demoResponses["refund"];

      const badge =
        response.action === "auto_reply"
          ? "✅ Auto-Resolved"
          : response.action === "clarify"
          ? "🟡 Clarifying"
          : "🔵 Escalated";

      setMessages((prev) => [
        ...prev,
        { role: "bot", text: `${badge}\n\n${response.text}` },
      ]);
    }, 800);
  };

  return (
    <section style={{ padding: "80px 0" }}>
      <div className="container-narrow">
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <h2 style={{ fontSize: 32, marginBottom: 12 }}>Try It Live</h2>
          <p style={{ color: "var(--slate-500)", fontSize: 16 }}>
            Type <strong>&quot;Where is my invoice?&quot;</strong>,{" "}
            <strong>&quot;I want a refund&quot;</strong>, or{" "}
            <strong>&quot;Talk to a human&quot;</strong>
          </p>
        </div>

        <div
          className="card"
          style={{
            maxWidth: 440,
            margin: "0 auto",
            padding: 0,
            overflow: "hidden",
            boxShadow: "0 8px 40px rgba(0,0,0,0.08)",
          }}
        >
          {/* Header */}
          <div
            style={{
              background: "var(--primary)",
              color: "white",
              padding: "16px 20px",
              fontWeight: 600,
              fontSize: 15,
              display: "flex",
              alignItems: "center",
              gap: 10,
            }}
          >
            <div
              style={{
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: "#86efac",
              }}
            />
            ResolveAI Support
          </div>

          {/* Messages */}
          <div
            style={{
              height: 300,
              overflowY: "auto",
              padding: 20,
              display: "flex",
              flexDirection: "column",
              gap: 12,
              background: "var(--slate-50)",
            }}
          >
            {messages.map((msg, i) => (
              <div
                key={i}
                style={{
                  alignSelf: msg.role === "user" ? "flex-end" : "flex-start",
                  maxWidth: "80%",
                  padding: "10px 14px",
                  borderRadius:
                    msg.role === "user"
                      ? "14px 14px 4px 14px"
                      : "14px 14px 14px 4px",
                  background:
                    msg.role === "user" ? "var(--primary)" : "var(--white)",
                  color:
                    msg.role === "user" ? "white" : "var(--slate-700)",
                  fontSize: 13,
                  lineHeight: 1.5,
                  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                  whiteSpace: "pre-wrap",
                }}
              >
                {msg.text}
              </div>
            ))}
          </div>

          {/* Input */}
          <div
            style={{
              display: "flex",
              borderTop: "1px solid var(--slate-200)",
              padding: 12,
              gap: 8,
              background: "white",
            }}
          >
            <input
              className="input"
              placeholder="Type a message..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSend()}
              style={{ flex: 1, fontSize: 13 }}
            />
            <button
              className="btn btn-primary"
              onClick={handleSend}
              style={{ padding: "8px 16px", fontSize: 13 }}
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}

/* ---------- CTA ---------- */
function CTA() {
  return (
    <section
      style={{
        padding: "80px 0",
        background: "var(--slate-900)",
        textAlign: "center",
      }}
    >
      <div className="container-narrow">
        <h2
          style={{
            fontSize: 36,
            color: "white",
            marginBottom: 16,
            fontWeight: 800,
          }}
        >
          Ready to Automate Your Support?
        </h2>
        <p
          style={{
            color: "var(--slate-400)",
            fontSize: 17,
            maxWidth: 500,
            margin: "0 auto 32px",
          }}
        >
          Start resolving tickets with AI in minutes. Free tier available with OpenRouter and local embeddings.
        </p>
        <a
          href="/register"
          className="btn btn-primary"
          style={{
            padding: "16px 40px",
            fontSize: 16,
            fontWeight: 600,
          }}
        >
          Get Started Free →
        </a>
      </div>
    </section>
  );
}

/* ---------- Footer ---------- */
function Footer() {
  return (
    <footer
      style={{
        padding: "32px 0",
        borderTop: "1px solid var(--slate-100)",
        textAlign: "center",
      }}
    >
      <div className="container-narrow">
        <p style={{ color: "var(--slate-400)", fontSize: 13 }}>
          © 2026 ResolveAI · Powered by{" "}
          <a
            href="https://github.com/endee-io/endee"
            target="_blank"
            style={{ color: "var(--slate-500)" }}
          >
            Endee
          </a>{" "}
          &{" "}
          <a
            href="https://openrouter.ai"
            target="_blank"
            style={{ color: "var(--slate-500)" }}
          >
            OpenRouter
          </a>
        </p>
      </div>
    </footer>
  );
}
