"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken, setToken, type CurrentUser, type RegulatoryDossier, type RegulatoryProduct } from "@/lib/api";
import { ThemeSwitcher } from "@/lib/theme";
import { IntelligenceDashboard, IntelligenceWidget } from "@/components/IntelligenceWidgets";

const NAV_ITEMS = ["Dashboard", "Products", "Regulatory", "Submissions", "Intelligence", "Documents", "Workflows", "More"];

// Dossier lifecycle (spec Layer 2 §14) mirrored here just for a
// next-step suggestion in the UI — the real state machine and RBAC
// check live server-side in dossier_service; this is a shortcut label,
// not a second source of truth.
const NEXT_STATUS: Record<string, string | null> = {
  DRAFT: "UNDER_REVIEW",
  UNDER_REVIEW: "ACTIVE",
  ACTIVE: "LOCKED",
  LOCKED: null,
  ARCHIVED: null,
};

function ProductsPanel() {
  const [products, setProducts] = useState<RegulatoryProduct[]>([]);
  const [dossiersByProduct, setDossiersByProduct] = useState<Record<string, RegulatoryDossier[]>>({});
  const [expanded, setExpanded] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.products().then(setProducts).catch((e) => setError(e.message));
  }, []);

  async function toggleExpand(productId: string) {
    if (expanded === productId) {
      setExpanded(null);
      return;
    }
    setExpanded(productId);
    if (!dossiersByProduct[productId]) {
      try {
        const dossiers = await api.dossiers(productId);
        setDossiersByProduct((prev) => ({ ...prev, [productId]: dossiers }));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load dossiers");
      }
    }
  }

  async function advance(dossier: RegulatoryDossier) {
    const next = NEXT_STATUS[dossier.status];
    if (!next) return;
    try {
      const updated = await api.transitionDossier(dossier.id, next);
      setDossiersByProduct((prev) => ({
        ...prev,
        [dossier.product_id]: prev[dossier.product_id].map((d) => (d.id === dossier.id ? updated : d)),
      }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Transition failed — you may not hold the permission this step requires");
    }
  }

  return (
    <div>
      <h1 className="mb-4">Products</h1>
      {error && <p className="mb-3 text-sm text-red-600">{error}</p>}
      {products.length === 0 && !error && <p className="text-sm text-ink/50">No products yet.</p>}
      <div className="space-y-2">
        {products.map((product) => (
          <div key={product.id} className="rounded-lg bg-surface shadow-sm">
            <button
              onClick={() => toggleExpand(product.id)}
              className="flex w-full items-center justify-between px-4 py-3 text-left"
            >
              <div>
                <div className="font-medium">{product.name}</div>
                <div className="text-xs text-ink/50">
                  {product.active_ingredient || "—"} · {product.dosage_form || "—"}
                </div>
              </div>
              <span className="text-xs text-ink/40">{expanded === product.id ? "Hide dossiers" : "Show dossiers"}</span>
            </button>
            {expanded === product.id && (
              <div className="border-t border-black/5 px-4 py-3">
                {(dossiersByProduct[product.id] || []).map((dossier) => (
                  <div key={dossier.id} className="flex items-center justify-between py-1.5 text-sm">
                    <span>
                      {dossier.ctd_standard} v{dossier.standard_version} · {dossier.region}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="rounded-full bg-accent-secondary px-2 py-0.5 text-xs">{dossier.status}</span>
                      {NEXT_STATUS[dossier.status] && (
                        <button onClick={() => advance(dossier)} className="text-xs text-accent underline">
                          Move to {NEXT_STATUS[dossier.status]}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
                {(dossiersByProduct[product.id] || []).length === 0 && (
                  <p className="text-sm text-ink/40">No dossiers for this product yet.</p>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [activeTab, setActiveTab] = useState("Dashboard");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken()) {
      router.push("/login");
      return;
    }
    api.me().then(setUser).catch(() => {
      setToken(null);
      router.push("/login");
    });
  }, [router]);

  function handleLogout() {
    setToken(null);
    router.push("/login");
  }

  if (!user) return null;

  return (
    <div className="min-h-screen bg-canvas">
      {/* Top navigation — spec §40: identity left, tabs center, actions
          right. Layer 1 uses one nav structure for both themes; only the
          tokens (colors/font/active-pill radius) differ (spec §38). */}
      <header className="flex items-center justify-between border-b border-black/5 bg-surface px-6 py-3">
        <div className="font-semibold">RAISA Synapse</div>
        <nav className="flex gap-1">
          {NAV_ITEMS.map((item) => (
            <button
              key={item}
              onClick={() => setActiveTab(item)}
              className={`px-3 py-1.5 text-sm ${activeTab === item ? "nav-tab-active" : "text-ink/70"}`}
            >
              {item}
            </button>
          ))}
        </nav>
        <div className="flex items-center gap-4 text-sm">
          <ThemeSwitcher />
          <span>{user.name}</span>
          <button onClick={handleLogout} className="text-ink/60 underline">
            Sign out
          </button>
        </div>
      </header>

      <main className="p-6">
        {activeTab === "Dashboard" ? (
          <>
            <h1 className="mb-4">Welcome back, {user.name.split(" ")[0]}</h1>

            {/* Foundation KPIs (spec §46) — zeros until Layer 2's
                Regulatory Master Data exists to count. */}
            <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
              {["Products", "Applications", "Registrations", "Submissions", "Documents", "Open Tasks"].map((kpi) => (
                <div key={kpi} className="rounded-lg bg-surface p-4 shadow-sm">
                  <div className="text-2xl font-semibold">0</div>
                  <div className="text-xs text-ink/60">{kpi}</div>
                </div>
              ))}
            </div>

            <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
              <div className="rounded-lg border border-dashed border-black/15 bg-surface/50 p-6">
                <div className="mb-1 font-medium">Action Center</div>
                <div className="text-sm text-ink/50">Coming in a future layer</div>
              </div>
              {/* Layer 3: the former "Global Intelligence" placeholder is
                  now a live widget on the same shared intelligence model. */}
              <IntelligenceWidget title="Latest Intelligence" limit={4} />
              <div className="rounded-lg border border-dashed border-black/15 bg-surface/50 p-6">
                <div className="mb-1 font-medium">RAISA Assistant</div>
                <div className="text-sm text-ink/50">Coming in a future layer</div>
              </div>
            </div>
          </>
        ) : activeTab === "Products" ? (
          <ProductsPanel />
        ) : activeTab === "Intelligence" ? (
          <IntelligenceDashboard />
        ) : (
          <div className="rounded-lg border border-dashed border-black/15 bg-surface/50 p-10 text-center">
            <div className="mb-1 font-medium">{activeTab}</div>
            <div className="text-sm text-ink/50">Coming in a future layer</div>
          </div>
        )}

        {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
      </main>
    </div>
  );
}
