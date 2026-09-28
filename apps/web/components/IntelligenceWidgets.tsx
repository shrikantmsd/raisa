"use client";

import { useEffect, useState } from "react";
import { intelligenceApi, type IntelligenceItem } from "@/lib/api";

// Spec §8 — five fixed impact levels. Semantic status colors (not
// theme tokens) on purpose: "critical" should read as critical in both
// RAISA Office and RAISA GenX, so these deliberately don't follow the
// theme's accent color.
const IMPACT_STYLES: Record<string, string> = {
  CRITICAL: "bg-red-100 text-red-800",
  HIGH: "bg-orange-100 text-orange-800",
  MEDIUM: "bg-yellow-100 text-yellow-800",
  LOW: "bg-blue-100 text-blue-800",
  INFORMATIONAL: "bg-gray-100 text-gray-700",
};

const TYPE_LABELS: Record<string, string> = {
  REGULATORY_GUIDELINE: "Guideline",
  REGULATORY_CHANGE: "Regulatory change",
  AGENCY_NEWS: "Agency news",
  INDUSTRY_NEWS: "Industry news",
  TENDER_ALERT: "Tender",
  PATENT_CLIFF: "Patent cliff",
  PARA_IV_CHALLENGE: "Para IV",
  PHARMA_EVENT: "Event",
  SAFETY_COMPLIANCE_ALERT: "Safety / compliance",
};

/** One intelligence item (spec §12). "View details" expands inline —
 * the same single-page-shell pattern the rest of the dashboard already
 * uses, rather than a separate detail route. */
export function IntelligenceCard({ item }: { item: IntelligenceItem }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-black/5 bg-surface p-3 text-sm">
      <div className="mb-1 flex items-start justify-between gap-2">
        <div className="font-medium leading-snug">{item.title}</div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${IMPACT_STYLES[item.impact_level] || IMPACT_STYLES.INFORMATIONAL}`}>
          {item.impact_level}
        </span>
      </div>
      <div className="text-xs text-ink/50">
        {TYPE_LABELS[item.intelligence_type] || item.intelligence_type}
        {item.country_region ? ` · ${item.country_region}` : ""}
        {item.publication_date ? ` · ${item.publication_date}` : ""}
        {item.scope === "GLOBAL" ? " · CoLAB" : ""}
      </div>
      <button onClick={() => setOpen(!open)} className="mt-1 text-xs text-accent underline">
        {open ? "Hide details" : "View details"}
      </button>
      {open && (
        <div className="mt-2 space-y-1 border-t border-black/5 pt-2 text-xs text-ink/70">
          <p>{item.summary}</p>
          {item.effective_date && <p>Effective: {item.effective_date}</p>}
          <p>
            <span className="text-ink/50">Impact basis:</span> {item.impact_reason}
          </p>
        </div>
      )}
    </div>
  );
}

/** One dashboard widget (spec §11). All seven widgets are this same
 * component with a different `intelligenceType` — one data model, one
 * API call shape, not seven systems. */
export function IntelligenceWidget({ title, intelligenceType, limit = 3 }: { title: string; intelligenceType?: string; limit?: number }) {
  const [items, setItems] = useState<IntelligenceItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    intelligenceApi
      .list({ intelligence_type: intelligenceType, status_filter: "PUBLISHED", limit })
      .then(setItems)
      .catch((e) => setError(e.message));
  }, [intelligenceType, limit]);

  return (
    <div className="rounded-lg bg-surface p-4 shadow-sm">
      <h2 className="mb-3 font-semibold">{title}</h2>
      {error && <p className="text-xs text-red-600">{error}</p>}
      {items === null && !error && <p className="text-xs text-ink/40">Loading…</p>}
      {items && items.length === 0 && <p className="text-xs text-ink/40">Nothing to show yet.</p>}
      <div className="space-y-2">
        {items?.map((item) => (
          <IntelligenceCard key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}

// The seven widgets spec §11 names, each mapped onto one of the nine
// intelligence types spec §3 defines. "Regulatory Alerts" maps to the
// safety/compliance type; the two other regulatory-flavored types
// (REGULATORY_CHANGE, AGENCY_NEWS) still surface via the Guidelines
// widget's sibling filters once a dedicated widget is wanted for them.
export const INTELLIGENCE_WIDGETS: { title: string; intelligenceType: string }[] = [
  { title: "Tender Alerts", intelligenceType: "TENDER_ALERT" },
  { title: "Patent Cliff Monitor", intelligenceType: "PATENT_CLIFF" },
  { title: "Para IV Challenge Tracker", intelligenceType: "PARA_IV_CHALLENGE" },
  { title: "Pharma Industry News", intelligenceType: "INDUSTRY_NEWS" },
  { title: "Guideline Updates", intelligenceType: "REGULATORY_GUIDELINE" },
  { title: "Upcoming Pharma Events", intelligenceType: "PHARMA_EVENT" },
  { title: "Regulatory Alerts", intelligenceType: "SAFETY_COMPLIANCE_ALERT" },
];

export function IntelligenceDashboard() {
  return (
    <div>
      <h1 className="mb-4">Regulatory Intelligence</h1>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {INTELLIGENCE_WIDGETS.map((w) => (
          <IntelligenceWidget key={w.title} title={w.title} intelligenceType={w.intelligenceType} />
        ))}
      </div>
    </div>
  );
}
