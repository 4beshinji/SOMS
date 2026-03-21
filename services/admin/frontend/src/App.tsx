import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { useAuth } from '@soms/auth';
import { Spinner } from '@soms/ui';
import { lazy, Suspense } from 'react';

const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const SpatialMonitorPage = lazy(() => import('./pages/SpatialMonitorPage'));
const InventoryPage = lazy(() => import('./pages/InventoryPage'));
const AnomalyPage = lazy(() => import('./pages/AnomalyPage'));
const TaskQueuePage = lazy(() => import('./pages/TaskQueuePage'));
const VoicePage = lazy(() => import('./pages/VoicePage'));
const EconomyPage = lazy(() => import('./pages/EconomyPage'));
const ShoppingPage = lazy(() => import('./pages/ShoppingPage'));
const ZoneEditor = lazy(() => import('./pages/ZoneEditor'));
const CameraSetupPage = lazy(() => import('./pages/CameraSetupPage'));

function LoginRedirect() {
  return (
    <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
      <div className="w-full max-w-sm space-y-8 text-center px-6">
        <div>
          <h1 className="text-5xl font-bold text-[var(--primary-500)]">SOMS</h1>
          <p className="text-[var(--gray-600)] mt-2">Admin Console</p>
        </div>
        <div className="bg-white rounded-2xl p-8 elevation-2">
          <h2 className="text-lg font-semibold text-[var(--gray-900)] mb-2">サインイン</h2>
          <p className="text-sm text-[var(--gray-500)] mb-6">管理者アカウントでログインしてください</p>
          <div className="space-y-3">
            <a
              href="/api/auth/slack/login"
              className="w-full py-3 bg-[#4A154B] hover:bg-[#611f64] text-white font-semibold rounded-xl flex items-center justify-center gap-2.5 transition-colors"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M5.042 15.165a2.528 2.528 0 0 1-2.52 2.523A2.528 2.528 0 0 1 0 15.165a2.527 2.527 0 0 1 2.522-2.52h2.52v2.52zm1.271 0a2.527 2.527 0 0 1 2.521-2.52 2.527 2.527 0 0 1 2.521 2.52v6.313A2.528 2.528 0 0 1 8.834 24a2.528 2.528 0 0 1-2.521-2.522v-6.313zM8.834 5.042a2.528 2.528 0 0 1-2.521-2.52A2.528 2.528 0 0 1 8.834 0a2.528 2.528 0 0 1 2.521 2.522v2.52H8.834zm0 1.271a2.528 2.528 0 0 1 2.521 2.521 2.528 2.528 0 0 1-2.521 2.521H2.522A2.528 2.528 0 0 1 0 8.834a2.528 2.528 0 0 1 2.522-2.521h6.312zm10.124 2.521a2.528 2.528 0 0 1 2.52-2.521A2.528 2.528 0 0 1 24 8.834a2.528 2.528 0 0 1-2.522 2.521h-2.52V8.834zm-1.271 0a2.528 2.528 0 0 1-2.521 2.521 2.528 2.528 0 0 1-2.521-2.521V2.522A2.528 2.528 0 0 1 15.165 0a2.528 2.528 0 0 1 2.522 2.522v6.312zm-2.522 10.124a2.528 2.528 0 0 1 2.522 2.52A2.528 2.528 0 0 1 15.165 24a2.527 2.527 0 0 1-2.521-2.522v-2.52h2.521zm0-1.271a2.527 2.527 0 0 1-2.521-2.521 2.528 2.528 0 0 1 2.521-2.521h6.313A2.528 2.528 0 0 1 24 15.165a2.528 2.528 0 0 1-2.522 2.522h-6.313z" />
              </svg>
              Slack でサインイン
            </a>
            <a
              href="/api/auth/github/login"
              className="w-full py-3 bg-[var(--gray-800)] hover:bg-[var(--gray-700)] text-white font-semibold rounded-xl flex items-center justify-center gap-2.5 transition-colors"
            >
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 0C5.374 0 0 5.373 0 12c0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23A11.509 11.509 0 0 1 12 5.803c1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576C20.566 21.797 24 17.3 24 12c0-6.627-5.373-12-12-12z" />
              </svg>
              GitHub でサインイン
            </a>
          </div>
        </div>
        <p className="text-[var(--gray-400)] text-xs">Symbiotic Office Management System</p>
      </div>
    </div>
  );
}

function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="h-screen bg-[var(--gray-50)] flex overflow-hidden">
      {/* Sidebar */}
      <nav className="w-56 bg-white border-r border-[var(--gray-200)] flex flex-col flex-shrink-0 overflow-y-auto">
        <div className="p-4 border-b border-[var(--gray-200)]">
          <h1 className="text-lg font-bold text-[var(--gray-900)]">SOMS Admin</h1>
        </div>
        <div className="flex-1 py-2">
          <NavLink
            to="/analytics"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Analytics
          </NavLink>
          <NavLink
            to="/spatial"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Spatial Monitor
          </NavLink>
          <NavLink
            to="/inventory"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Inventory
          </NavLink>
          <NavLink
            to="/shopping"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Shopping
          </NavLink>
          <NavLink
            to="/task-queue"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Task Queue
          </NavLink>
          <NavLink
            to="/anomaly"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Anomaly
          </NavLink>
          <NavLink
            to="/voice"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Voice
          </NavLink>
          <NavLink
            to="/economy"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Economy
          </NavLink>
          <NavLink
            to="/cameras"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Camera Setup
          </NavLink>
          <NavLink
            to="/zone-editor"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Zone Editor
          </NavLink>
        </div>
        <div className="p-4 border-t border-[var(--gray-200)]">
          <p className="text-xs text-[var(--gray-500)] mb-2">{user?.display_name || user?.username}</p>
          <button
            onClick={() => logout()}
            className="text-xs text-[var(--error-600)] hover:text-[var(--error-700)]"
          >
            Sign out
          </button>
        </div>
      </nav>

      {/* Main content */}
      <main className="flex-1 overflow-auto min-h-0">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-24">
              <Spinner size="large" className="text-[var(--primary-500)]" />
            </div>
          }
        >
          <Routes>
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/spatial" element={<SpatialMonitorPage />} />

            <Route path="/inventory" element={<InventoryPage />} />
            <Route path="/shopping" element={<ShoppingPage />} />
            <Route path="/task-queue" element={<TaskQueuePage />} />
            <Route path="/anomaly" element={<AnomalyPage />} />
            <Route path="/voice" element={<VoicePage />} />
            <Route path="/economy" element={<EconomyPage />} />
            <Route path="/cameras" element={<CameraSetupPage />} />
            <Route path="/zone-editor" element={<ZoneEditor />} />
            <Route path="*" element={<Navigate to="/analytics" replace />} />
          </Routes>
        </Suspense>
      </main>
    </div>
  );
}

export default function App() {
  const { isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
        <Spinner size="large" className="text-[var(--primary-500)]" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <LoginRedirect />;
  }

  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
          <Spinner size="large" className="text-[var(--primary-500)]" />
        </div>
      }
    >
      <Routes>
        <Route path="*" element={<Layout />} />
      </Routes>
    </Suspense>
  );
}
