import { Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { useAuth } from '@soms/auth';
import { Spinner } from '@soms/ui';
import { lazy, Suspense } from 'react';

const AnalyticsPage = lazy(() => import('./pages/AnalyticsPage'));
const FloorPlanPage = lazy(() => import('./pages/FloorPlanPage'));

function LoginRedirect() {
  // Redirect to auth login
  return (
    <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
      <div className="text-center space-y-4">
        <h1 className="text-2xl font-bold text-[var(--gray-900)]">SOMS Admin</h1>
        <p className="text-[var(--gray-600)]">Please log in to continue.</p>
        <div className="flex gap-3 justify-center">
          <a
            href="/api/auth/slack/login"
            className="px-6 py-2.5 bg-[var(--primary-500)] text-white rounded-lg font-medium hover:bg-[var(--primary-600)] transition-colors"
          >
            Sign in with Slack
          </a>
          <a
            href="/api/auth/github/login"
            className="px-6 py-2.5 bg-[var(--gray-800)] text-white rounded-lg font-medium hover:bg-[var(--gray-900)] transition-colors"
          >
            Sign in with GitHub
          </a>
        </div>
      </div>
    </div>
  );
}

function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen bg-[var(--gray-50)] flex">
      {/* Sidebar */}
      <nav className="w-56 bg-white border-r border-[var(--gray-200)] flex flex-col">
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
            to="/floor-plan"
            className={({ isActive }) =>
              `block px-4 py-2.5 text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-[var(--primary-50)] text-[var(--primary-700)] border-r-2 border-[var(--primary-500)]'
                  : 'text-[var(--gray-700)] hover:bg-[var(--gray-100)]'
              }`
            }
          >
            Floor Plan
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
      <main className="flex-1 overflow-auto">
        <Suspense
          fallback={
            <div className="flex items-center justify-center py-24">
              <Spinner size="large" className="text-[var(--primary-500)]" />
            </div>
          }
        >
          <Routes>
            <Route path="/analytics" element={<AnalyticsPage />} />
            <Route path="/floor-plan" element={<FloorPlanPage />} />
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

  return <Layout />;
}
