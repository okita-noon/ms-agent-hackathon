import { useState, useRef, useEffect, type ReactNode } from "react";
import Header from "./components/Header";
import Orders from "./pages/Orders";
import Customers from "./pages/Customers";
import Inventory from "./pages/Inventory";
import { getTenantId, setTenantId } from "./lib/api";

type Tab = "orders" | "customers" | "inventory";

const TABS: { id: Tab; label: string; icon: ReactNode }[] = [
  {
    id: "orders",
    label: "受注管理",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    id: "inventory",
    label: "在庫管理",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    id: "customers",
    label: "顧客管理",
    icon: (
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
];

const TENANTS = [
  { id: "T-001", label: "T-001 丸山食品" },
  { id: "T-002", label: "T-002 鈴木青果" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("orders");
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });
  const [tenantId, setTenantIdState] = useState<string>(getTenantId());

  useEffect(() => {
    const el = tabRefs.current[tab];
    if (el) {
      const parent = el.parentElement!;
      setIndicator({
        left: el.offsetLeft - parent.offsetLeft,
        width: el.offsetWidth,
      });
    }
  }, [tab]);

  function handleTenantChange(id: string) {
    setTenantId(id);
    setTenantIdState(id);
  }

  return (
    <div className="min-h-screen bg-surface">
      <Header />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <nav className="relative mb-8">
          <div className="flex items-end gap-1 border-b border-gray-200 relative">
            {TABS.map((t) => (
              <button
                key={t.id}
                ref={(el) => { tabRefs.current[t.id] = el; }}
                onClick={() => setTab(t.id)}
                className={`flex items-center gap-2 px-5 py-3 text-sm font-medium -mb-px transition-colors duration-200 ${
                  tab === t.id
                    ? "text-brand-700"
                    : "text-gray-400 hover:text-gray-600"
                }`}
              >
                {t.icon}
                {t.label}
              </button>
            ))}
            <span
              className="tab-indicator absolute bottom-0 h-0.5 bg-brand-600 rounded-full"
              style={{ left: indicator.left, width: indicator.width }}
            />
            {/* Tenant selector — pushed to the right of the tab bar */}
            <div className="ml-auto mb-1 flex items-center gap-2">
              <span className="text-[11px] text-gray-400 font-medium tracking-wide">テナント</span>
              <div className="flex rounded-md border border-gray-200 overflow-hidden text-xs font-medium">
                {TENANTS.map((t, i) => (
                  <button
                    key={t.id}
                    onClick={() => handleTenantChange(t.id)}
                    className={`px-3 py-1.5 transition-colors duration-150 ${
                      tenantId === t.id
                        ? "bg-brand-600 text-white"
                        : "bg-white text-gray-500 hover:bg-gray-50"
                    } ${i > 0 ? "border-l border-gray-200" : ""}`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </nav>
        {tab === "orders" ? (
          <Orders key={tenantId} />
        ) : tab === "inventory" ? (
          <Inventory key={tenantId} />
        ) : (
          <Customers key={tenantId} />
        )}
      </main>
    </div>
  );
}
