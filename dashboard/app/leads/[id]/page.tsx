"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { LeadDetail } from "@/lib/types";
import { WarmingBanner } from "@/components/WarmingBanner";
import { LeadDetailView } from "@/components/LeadDetailView";

export default function LeadPage() {
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<LeadDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api.lead(params.id).then(setData).catch((e) => setErr(e?.message ?? "error"));
  }, [params.id]);

  if (err) return <p style={{ color: "var(--bad)" }}>Error: {err}</p>;
  if (!data) return <WarmingBanner />;

  return (
    <>
      <p>
        <Link href="/">← back to kanban</Link>
      </p>
      <LeadDetailView data={data} />
    </>
  );
}
