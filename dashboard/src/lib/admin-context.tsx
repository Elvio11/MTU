"use client";

import React, { createContext, useContext, useEffect, useState, ReactNode, useCallback } from 'react';

interface AdminContextType {
  isAdmin: boolean;
  isAdminMode: boolean;
  enableAdmin: (otp: string) => boolean;
  disableAdmin: () => void;
  requiresOTP: (action: string) => boolean;
}

const AdminContext = createContext<AdminContextType | undefined>(undefined);

const ADMIN_ACTIONS = ['killswitch', 'pause', 'resume', 'exit_position', 'sweep'];

export function AdminProvider({ children }: { children: ReactNode }) {
  const [isAdmin, setIsAdmin] = useState(false);
  const [isAdminMode, setIsAdminMode] = useState(() => {
    if (typeof window === 'undefined') return false;
    return localStorage.getItem('mtus_admin_mode') === 'true';
  });

  const enableAdmin = useCallback((otp: string): boolean => {
    if (typeof window === 'undefined') return false;
    
    const storedOTP = localStorage.getItem('mtus_otp_seed');
    if (!storedOTP) {
      setIsAdmin(true);
      setIsAdminMode(true);
      localStorage.setItem('mtus_admin_mode', 'true');
      return true;
    }

    const valid = otp === storedOTP;
    if (valid) {
      setIsAdmin(true);
      setIsAdminMode(true);
      localStorage.setItem('mtus_admin_mode', 'true');
    }
    return valid;
  }, []);

  const disableAdmin = useCallback(() => {
    setIsAdmin(false);
    setIsAdminMode(false);
    localStorage.removeItem('mtus_admin_mode');
  }, []);

  const requiresOTP = useCallback((action: string): boolean => {
    return isAdminMode && ADMIN_ACTIONS.includes(action);
  }, [isAdminMode]);

  return (
    <AdminContext.Provider value={{ isAdmin, isAdminMode, enableAdmin, disableAdmin, requiresOTP }}>
      {children}
    </AdminContext.Provider>
  );
}

export function useAdmin() {
  const context = useContext(AdminContext);
  if (!context) {
    throw new Error('useAdmin must be used within an AdminProvider');
  }
  return context;
}