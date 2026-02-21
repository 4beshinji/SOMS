import { useContext } from 'react';
import { AuthContext, type AuthContextType } from './AuthContext';

export function useAuth(): AuthContextType {
  return useContext(AuthContext);
}
