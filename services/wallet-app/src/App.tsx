import { Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { useAuth } from './auth/AuthContext';
import LoginPage from './auth/LoginPage';
import CallbackPage from './auth/CallbackPage';
import BottomNav from './components/BottomNav';
import Home from './pages/Home';
import Scan from './pages/Scan';
import Send from './pages/Send';
import History from './pages/History';
import Invest from './pages/Invest';
import DeviceDetail from './pages/DeviceDetail';

function AppRoutes() {
  const { user, isAuthenticated, isLoading } = useAuth();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-gray-400">Loading...</div>
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
    <AuthProvider>
      <div className="min-h-screen bg-gray-950 text-white">
        <AppRoutes />
      </div>
    </AuthProvider>
  );
}
