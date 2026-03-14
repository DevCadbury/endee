import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "ResolveAI — AI Customer Support Platform",
  description:
    "Production-ready AI customer support automation. Auto-resolve repeatable issues, intelligently escalate complex ones, and continuously learn from your team.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
