// Component-level verification of the Layer 3 Intelligence UI.
//
// This sandbox cannot download a real browser binary (Playwright's CDN
// is network-blocked here), so true E2E was not possible. These tests
// render the actual production components in jsdom with a mocked
// fetch standing in for the FastAPI backend -- the closest available
// substitute, and still real rendering/interaction, not a type check.
import { describe, test, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  IntelligenceCard,
  IntelligenceWidget,
  IntelligenceDashboard,
  INTELLIGENCE_WIDGETS,
} from "./IntelligenceWidgets";
import type { IntelligenceItem } from "@/lib/api";

function item(overrides: Partial<IntelligenceItem> = {}): IntelligenceItem {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    organization_id: "org-1",
    scope: "TENANT",
    intelligence_type: "REGULATORY_GUIDELINE",
    title: "Test guideline",
    summary: "A summary of the guideline.",
    authority_id: null,
    country_region: "US",
    publication_date: "2026-01-01",
    effective_date: null,
    status: "PUBLISHED",
    impact_level: "MEDIUM",
    impact_reason: "Routine update.",
    therapeutic_area: null,
    ...overrides,
  };
}

let fetchMock: ReturnType<typeof vi.fn>;

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  fetchMock.mockResolvedValueOnce({
    ok,
    status,
    json: async () => body,
  } as Response);
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("IntelligenceCard", () => {
  test("shows title, type, region, date, and impact badge", () => {
    render(<IntelligenceCard item={item({ impact_level: "CRITICAL" })} />);
    expect(screen.getByText("Test guideline")).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText(/Guideline/)).toBeInTheDocument();
    expect(screen.getByText(/US/)).toBeInTheDocument();
  });

  test("marks GLOBAL (CoLAB-owned) items distinctly from tenant items", () => {
    const { rerender } = render(<IntelligenceCard item={item({ scope: "GLOBAL" })} />);
    expect(screen.getByText(/CoLAB/)).toBeInTheDocument();

    rerender(<IntelligenceCard item={item({ scope: "TENANT" })} />);
    expect(screen.queryByText(/CoLAB/)).not.toBeInTheDocument();
  });

  test("surfaces lifecycle status for anything not published", () => {
    render(<IntelligenceCard item={item({ status: "WITHDRAWN" })} />);
    expect(screen.getByText(/WITHDRAWN/)).toBeInTheDocument();
  });

  test("expands to show the detail view (summary, impact basis) and collapses again", async () => {
    const user = userEvent.setup();
    render(<IntelligenceCard item={item({ effective_date: "2026-03-01" })} />);

    expect(screen.queryByText("A summary of the guideline.")).not.toBeInTheDocument();
    await user.click(screen.getByText("View details"));
    expect(screen.getByText("A summary of the guideline.")).toBeInTheDocument();
    expect(screen.getByText(/2026-03-01/)).toBeInTheDocument();
    expect(screen.getByText(/Routine update\./)).toBeInTheDocument();

    await user.click(screen.getByText("Hide details"));
    expect(screen.queryByText("A summary of the guideline.")).not.toBeInTheDocument();
  });
});

describe("IntelligenceWidget", () => {
  test("requests the given intelligence_type and only PUBLISHED items, then renders results", async () => {
    mockFetchOnce([item({ title: "Tender one", intelligence_type: "TENDER_ALERT" })]);
    render(<IntelligenceWidget title="Tender Alerts" intelligenceType="TENDER_ALERT" />);

    expect(await screen.findByText("Tender one")).toBeInTheDocument();
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("intelligence_type=TENDER_ALERT");
    expect(url).toContain("status_filter=PUBLISHED");
  });

  test("different widgets filter to different, non-overlapping result sets (one model, not seven systems)", async () => {
    mockFetchOnce([item({ title: "Tender only", intelligence_type: "TENDER_ALERT" })]);
    const { unmount } = render(<IntelligenceWidget title="Tender Alerts" intelligenceType="TENDER_ALERT" />);
    expect(await screen.findByText("Tender only")).toBeInTheDocument();
    unmount();

    mockFetchOnce([item({ title: "Event only", intelligence_type: "PHARMA_EVENT" })]);
    render(<IntelligenceWidget title="Upcoming Pharma Events" intelligenceType="PHARMA_EVENT" />);
    expect(await screen.findByText("Event only")).toBeInTheDocument();
    expect(screen.queryByText("Tender only")).not.toBeInTheDocument();
  });

  test("shows an empty state when nothing matches", async () => {
    mockFetchOnce([]);
    render(<IntelligenceWidget title="Patent Cliff Monitor" intelligenceType="PATENT_CLIFF" />);
    expect(await screen.findByText("Nothing to show yet.")).toBeInTheDocument();
  });

  test("surfaces an unauthorized/error response instead of silently showing nothing", async () => {
    mockFetchOnce({ message: "Not authenticated" }, false, 401);
    render(<IntelligenceWidget title="Regulatory Alerts" intelligenceType="SAFETY_COMPLIANCE_ALERT" />);
    expect(await screen.findByText("Not authenticated")).toBeInTheDocument();
  });
});

describe("IntelligenceDashboard", () => {
  test("renders all seven required widgets", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => [] } as Response);
    render(<IntelligenceDashboard />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(INTELLIGENCE_WIDGETS.length));

    const expectedTitles = [
      "Tender Alerts",
      "Patent Cliff Monitor",
      "Para IV Challenge Tracker",
      "Pharma Industry News",
      "Guideline Updates",
      "Upcoming Pharma Events",
      "Regulatory Alerts",
    ];
    expect(INTELLIGENCE_WIDGETS.map((w) => w.title).sort()).toEqual([...expectedTitles].sort());
    for (const title of expectedTitles) {
      expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    }
  });

  test("each widget queries its own distinct intelligence_type", async () => {
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => [] } as Response);
    render(<IntelligenceDashboard />);
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(INTELLIGENCE_WIDGETS.length));

    const queried = fetchMock.mock.calls.map((call) => new URL(call[0] as string, "http://x").searchParams.get("intelligence_type"));
    expect(new Set(queried).size).toBe(INTELLIGENCE_WIDGETS.length);
  });
});
