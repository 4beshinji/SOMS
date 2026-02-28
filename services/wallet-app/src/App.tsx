import { Routes, Route, Navigate } from 'react-router-dom';
import { useAuth } from './auth/AuthContext';
import LoginPage from './auth/LoginPage';
import CallbackPage from './auth/CallbackPage';
import BottomNav from './components/BottomNav';
import Home from './pages/Home';
import Tasks from './pages/Tasks';
import Scan from './pages/Scan';
import Send from './pages/Send';
import History from './pages/History';
import Invest from './pages/Invest';
import DeviceDetail from './pages/DeviceDetail';
import { Spinner } from '@soms/ui';

function AppRoutes() {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[var(--gray-50)]">
        <Spinner size="large" className="text-[var(--primary-500)]" />
      </div>
    );
  }

  if (!isAuthenticated || !user) {
    return (
      <Routes>
        <Route path="/auth/callback" element={<CallbackPage />} />
        <Route path="*" element={<LoginPage />} />
      </Routes>
    );
  }

  return (
    <>
      <Routes>
        <Route path="/" element={<Home userId={user.id} />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/scan" element={<Scan userId={user.id} />} />
        <Route path="/send" element={<Send userId={user.id} />} />
        <Route path="/history" element={<History userId={user.id} />} />
        <Route path="/invest" element={<Invest userId={user.id} />} />
        <Route path="/invest/device/:deviceId" element={<DeviceDetail userId={user.id} />} />
        <Route path="/auth/callback" element={<CallbackPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
      <BottomNav />
    </>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-[var(--gray-50)] text-[var(--gray-900)]">
      <AppRoutes />
    </div>
  );
}
