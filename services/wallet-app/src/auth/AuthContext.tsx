import { createContext, useContext } from 'react';

export interface AuthUser {
  id: number;
  username: string;
  display_name: string | null;
}

export interface AuthContextType {
  user: AuthUser | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (provider: 'slack' | 'github') => void;
  logout: () => void;
}

export const AuthContext = createContext<AuthContextType>({
  user: null,
  isAuthenticated: false,
  isLoading: true,
  login: () => {},
  logout: () => {},
});

export function useAuth(): AuthContextType {
  return useContext(AuthContext);
}
