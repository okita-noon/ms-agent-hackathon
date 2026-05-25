import { Suspense, lazy, type ReactNode } from "react";
import {
  Routes,
  Route,
  Navigate,
  NavLink,
} from "react-router-dom";
import Header from "./components/Header";
import LoadingState from "./components/LoadingState";
import { AuthProvider } from "./auth/AuthContext";
import { useAuth } from "./auth/useAuth";

const Login = lazy(() => import("./pages/Login"));

const Orders = lazy(() => import("./pages/Orders"));
const Customers = lazy(() => import("./pages/Customers"));
const Inventory = lazy(() => import("./pages/Inventory"));
const Analytics = lazy(() => import("./pages/Analytics"));
const PhoneDebug = lazy(() => import("./pages/PhoneDebug"));

type NavItem = { to: string; label: string; icon: ReactNode };

const BASE_NAV_ITEMS: NavItem[] = [
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

const DEV_NAV_ITEMS: NavItem[] = [
  {
    to: "/phone-debug",
    label: "電話DB",
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
      </svg>
    ),
  },
];

const NAV_ITEMS = (import.meta.env.DEV || localStorage.getItem("debug_nav") === "1")
  ? [...BASE_NAV_ITEMS, ...DEV_NAV_ITEMS]
  : BASE_NAV_ITEMS;

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

function PageFallback() {
  return (
    <LoadingState
      compact
      title="画面を読み込んでいます"
      message="必要なモジュールだけを読み込んでいます"
    />
  );
}

function DashboardLayout() {
  return (
    <div className="min-h-screen bg-surface flex flex-col">
      <Header />
      <div className="flex flex-1 overflow-hidden">
        <Sidebar />
        <main className="flex-1 overflow-y-auto px-6 lg:px-8 py-6">
          <div className="max-w-6xl">
            <Suspense fallback={<PageFallback />}>
              <Routes>
                <Route path="orders" element={<Orders />} />
                <Route path="inventory" element={<Inventory />} />
                <Route path="customers" element={<Customers />} />
                <Route path="analytics" element={<Analytics />} />
                <Route path="phone-debug" element={<PhoneDebug />} />
                <Route path="*" element={<Navigate to="/orders" replace />} />
              </Routes>
            </Suspense>
          </div>
        </main>
      </div>
    </div>
  );
}

/**
 * 認証状態に基づいてルートツリーを切り替える唯一のコンポーネント。
 * LoginRoute / RequireAuth という二重ガードをなくし、
 * user が truthy かどうかを1箇所で判定することで
 * concurrent rendering 下でのループを防ぐ。
 */
function AuthenticatedRouter() {
  const { user, isLoading } = useAuth();

  if (isLoading) return <LoadingScreen />;

  // 未認証: パスに関わらずログインフォームを表示
  if (!user) {
    return (
      <Routes>
        <Route
          path="*"
          element={
            <Suspense fallback={<LoadingScreen />}>
              <Login />
            </Suspense>
          }
        />
      </Routes>
    );
  }

  // 認証済み: /login に来たら /orders へ。その他はダッシュボード
  return (
    <Routes>
      <Route path="login" element={<Navigate to="/orders" replace />} />
      <Route path="/*" element={<DashboardLayout />} />
    </Routes>
  );
}

function AppRoutes() {
  return (
    <AuthProvider>
      <AuthenticatedRouter />
    </AuthProvider>
  );
}

export default function App() {
  return <AppRoutes />;
}
