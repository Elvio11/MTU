import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { AdminProvider, useAdmin } from './admin-context';
import React from 'react';

const store: Record<string, string> = {};

beforeEach(() => {
  vi.restoreAllMocks();
  Object.keys(store).forEach(key => delete store[key]);
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation((key: string) => store[key] ?? null);
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation((key: string, value: string) => { store[key] = value; });
  vi.spyOn(Storage.prototype, 'removeItem').mockImplementation((key: string) => { delete store[key]; });
});

describe('useAdmin', () => {
  it('throws without AdminProvider', () => {
    expect(() => renderHook(() => useAdmin())).toThrow('useAdmin must be used within an AdminProvider');
  });

  it('enables admin when no OTP seed is stored', () => {
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    act(() => { result.current.enableAdmin('any-otp'); });
    expect(result.current.isAdmin).toBe(true);
    expect(result.current.isAdminMode).toBe(true);
    expect(store['mtus_admin_mode']).toBe('true');
  });

  it('enables admin with correct OTP', () => {
    store['mtus_otp_seed'] = '123456';
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    act(() => { result.current.enableAdmin('123456'); });
    expect(result.current.isAdmin).toBe(true);
    expect(result.current.isAdminMode).toBe(true);
  });

  it('fails to enable admin with wrong OTP', () => {
    store['mtus_otp_seed'] = '123456';
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    act(() => { result.current.enableAdmin('wrong-otp'); });
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.isAdminMode).toBe(false);
  });

  it('disables admin mode', () => {
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    act(() => { result.current.enableAdmin('any-otp'); });
    expect(result.current.isAdminMode).toBe(true);
    act(() => { result.current.disableAdmin(); });
    expect(result.current.isAdmin).toBe(false);
    expect(result.current.isAdminMode).toBe(false);
    expect(store['mtus_admin_mode']).toBeUndefined();
  });

  it('requiresOTP returns false when admin mode is off', () => {
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    expect(result.current.requiresOTP('killswitch')).toBe(false);
  });

  it('requiresOTP returns true for valid actions when admin mode is on', () => {
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    act(() => { result.current.enableAdmin('any-otp'); });
    expect(result.current.requiresOTP('killswitch')).toBe(true);
    expect(result.current.requiresOTP('pause')).toBe(true);
    expect(result.current.requiresOTP('resume')).toBe(true);
    expect(result.current.requiresOTP('exit_position')).toBe(true);
    expect(result.current.requiresOTP('sweep')).toBe(true);
  });

  it('requiresOTP returns false for invalid actions when admin mode is on', () => {
    const { result } = renderHook(() => useAdmin(), { wrapper: AdminProvider });
    act(() => { result.current.enableAdmin('any-otp'); });
    expect(result.current.requiresOTP('unknown')).toBe(false);
  });
});
