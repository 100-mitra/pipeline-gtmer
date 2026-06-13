"use client";

// Shown while the first request to the backend is in flight — Render free web
// services cold-start in ~1 min, so a hang reads as intentional, not broken.
export function WarmingBanner() {
  return (
    <div className="warming">
      Waking the backend… Render free instances sleep after 15 min idle and take ~1 min to spin up.
    </div>
  );
}
