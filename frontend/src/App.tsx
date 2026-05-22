import { useEffect, type ReactNode } from "react";
import {
  Routes,
  Route,
  Navigate,
  NavLink,
  useNavigate,
} from "react-router-dom";
import Header from "./components/Header";
import LoadingState from "./components/LoadingState";
import Orders from "./pages/Orders";
import Customers from "./pages/Customers";
import Inventory from "./pages/Inventory";
import Analytics from "./pages/Analytics";
import Login from "./pages/Login";
import { AuthProvider, useAuth } from "./auth/AuthContext";

type NavItem = { to: string; label: string; icon: ReactNode };

const NAV_ITEMS: NavItem[] = [
  {
    to: "/orders",
    label: "受注",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
      </svg>
    ),
  },
  {
    to: "/inventory",
    label: "在庫",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4" />
      </svg>
    ),
  },
  {
    to: "/customers",
    label: "顧客",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
      </svg>
    ),
  },
  {
    to: "/analytics",
    label: "分析",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M11 3.055A9.001 9.001 0 1020.945 13H11V3.055z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M20.488 9H15V3.512A9.025 9.025 0 0120.488 9z" />
      </svg>
    ),
  },
];

function Sidebar() {
  return (
    <aside className="w-52 shrink-0 bg-white border-r border-gray-200 flex flex-col">
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) =>
              `w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? "bg-brand-50 text-brand-700"
                  : "text-gray-500 hover:text-gray-900 hover:bg-gray-50"
              }`
            }
          >
            {({ isActive }) => (
              <>
                <span className={isActive ? "text-brand-600" : "text-gray-400"}>
                  {item.icon}
                </span>
                {item.label}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}

function LoadingScreen() {
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

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && !user) {
      navigate("/login", { replace: true });
    }
  }, [isLoading, user, navigate]);

  if (isLoading) return <LoadingScreen />;
  if (!user) return <LoadingScreen />;

  return <>{children}</>;
}

function DashboardLayout() {
  return (
    <RequireAuth>
      <div className="min-h-screen bg-surface flex flex-col">
        <Header />
        <div className="flex flex-1 overflow-hidden">
          <Sidebar />
          <main className="flex-1 overflow-y-auto px-6 lg:px-8 py-6">
            <div className="max-w-6xl">
              <Routes>
                <Route path="orders" element={<Orders />} />
                <Route path="inventory" element={<Inventory />} />
                <Route path="customers" element={<Customers />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="*" element={<Navigate to="/orders" replace />} />
              </Routes>
            </div>
          </main>
        </div>
      </div>
    </RequireAuth>
  );
}

function LoginRoute() {
  const { user, isLoading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!isLoading && user) {
      navigate("/orders", { replace: true });
    }
  }, [isLoading, user, navigate]);

  if (isLoading) return <LoadingScreen />;
  if (user) return <LoadingScreen />;

  return <Login />;
}

function AppRoutes() {
  return (
    <AuthProvider>
      <Routes>
        <Route path="login" element={<LoginRoute />} />
        <Route path="/*" element={<DashboardLayout />} />
      </Routes>
    </AuthProvider>
  );
}

export default function App() {
  return <AppRoutes />;
}
