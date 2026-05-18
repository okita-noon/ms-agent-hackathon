import { useState, useRef, useEffect, type ReactNode } from "react";
import Header from "./components/Header";
import LoadingState from "./components/LoadingState";
import Orders from "./pages/Orders";
import Customers from "./pages/Customers";
import Inventory from "./pages/Inventory";
import Login from "./pages/Login";
import { AuthProvider, useAuth } from "./auth/AuthContext";

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

function Dashboard() {
  const [tab, setTab] = useState<Tab>("orders");
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

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
          </div>
        </nav>
        {tab === "orders" ? (
          <Orders />
        ) : tab === "inventory" ? (
          <Inventory />
        ) : (
          <Customers />
        )}
      </main>
    </div>
  );
}

function AppContent() {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="min-h-screen bg-surface">
        <LoadingState
          title="foogentを起動しています"
          message="受注データとログイン状態を確認中です"
          icon={
            <svg className="w-8 h-8 text-brand-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.7} d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          }
        />
      </div>
    );
  }

  return user ? <Dashboard /> : <Login />;
}

export default function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}
