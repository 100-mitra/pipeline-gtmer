import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "PipelineAgent — GTMer",
  description: "An autonomous AI-SDR pipeline run on GTMer's own ICP.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="wrap">
          <nav className="topnav">
            <h1>PipelineAgent</h1>
            <Link href="/">Kanban</Link>
            <Link href="/evals">Evals</Link>
            <span className="muted">prospect → research → draft → score → approve · emails never sent</span>
          </nav>
          {children}
        </div>
      </body>
    </html>
  );
}
