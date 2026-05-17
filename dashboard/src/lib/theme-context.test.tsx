import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { ThemeProvider, useTheme } from './theme-context';
import React from 'react';

const mediaListeners: Record<string, Function[]> = {};
let mediaQueryMatches = false;

beforeEach(() => {
  Object.keys(mediaListeners).forEach(k => delete mediaListeners[k]);
  mediaQueryMatches = false;
  vi.restoreAllMocks();
  vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null);
  vi.spyOn(Storage.prototype, 'setItem');
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    get matches() { return mediaQueryMatches; }, media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn((event: string, handler: Function) => {
      if (!mediaListeners[event]) mediaListeners[event] = [];
      mediaListeners[event].push(handler);
    }),
    removeEventListener: vi.fn((event: string, handler: Function) => {
      if (mediaListeners[event]) {
        mediaListeners[event] = mediaListeners[event].filter(h => h !== handler);
      }
    }),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
});

describe('useTheme', () => {
  it('throws without ThemeProvider', () => {
    expect(() => renderHook(() => useTheme())).toThrow('useTheme must be used within a ThemeProvider');
  });

  it('defaults to dark theme', () => {
    const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
    expect(result.current.theme).toBe('dark');
    expect(result.current.resolvedTheme).toBe('dark');
  });

  it('setTheme to light updates state and localStorage', () => {
    const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
    act(() => { result.current.setTheme('light'); });
    expect(result.current.theme).toBe('light');
    expect(result.current.resolvedTheme).toBe('light');
    expect(localStorage.setItem).toHaveBeenCalledWith('mtus_theme', 'light');
  });

  it('setTheme to system resolves to light when prefers-color-scheme is not dark', () => {
    const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
    act(() => { result.current.setTheme('system'); });
    expect(result.current.theme).toBe('system');
    expect(result.current.resolvedTheme).toBe('light');
  });

  it('setTheme to system resolves to dark when prefers-color-scheme is dark', () => {
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: true, media: query, onchange: null,
      addListener: vi.fn(), removeListener: vi.fn(),
      addEventListener: vi.fn(), removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })) as unknown as typeof window.matchMedia;
    const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
    act(() => { result.current.setTheme('system'); });
    expect(result.current.theme).toBe('system');
    expect(result.current.resolvedTheme).toBe('dark');
  });

  it('resolvedTheme matches theme when theme is not system', () => {
    const { result } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
    act(() => { result.current.setTheme('light'); });
    expect(result.current.resolvedTheme).toBe('light');
    act(() => { result.current.setTheme('dark'); });
    expect(result.current.resolvedTheme).toBe('dark');
  });

  it('updates classList when system theme media query changes', () => {
    const { result, unmount } = renderHook(() => useTheme(), { wrapper: ThemeProvider });
    act(() => { result.current.setTheme('system'); });
    expect(document.documentElement.classList.contains('light')).toBe(true);
    mediaQueryMatches = true;
    act(() => {
      mediaListeners['change']?.forEach((h: Function) => h());
    });
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    unmount();
    expect(mediaListeners['change']?.length || 0).toBe(0);
  });
});
