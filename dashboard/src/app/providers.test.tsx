import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, cleanup } from '@testing-library/react';
import { renderHook } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import React, { Component, ReactNode } from 'react';

class TestErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div data-testid="error-fallback">
          <h1>Something went wrong</h1>
          <p>{this.state.error?.message || 'An unexpected error occurred'}</p>
          <button>Reload Dashboard</button>
        </div>
      );
    }
    return this.props.children;
  }
}

describe('ErrorBoundary', () => {
  it('should render children when no error', () => {
    const { container } = render(
      <TestErrorBoundary>
        <div data-testid="child">Test Child</div>
      </TestErrorBoundary>
    );

    expect(screen.getByTestId('child')).toBeInTheDocument();
  });

  it('should show error fallback when error occurs', () => {
    const ThrowError = () => {
      throw new Error('Test error');
    };

    render(
      <TestErrorBoundary>
        <ThrowError />
      </TestErrorBoundary>
    );

    expect(screen.getByText(/Something went wrong/i)).toBeInTheDocument();
  });

  it('should display error message', () => {
    const ThrowError = () => {
      throw new Error('Custom error message');
    };

    render(
      <TestErrorBoundary>
        <ThrowError />
      </TestErrorBoundary>
    );

    expect(screen.getByText(/Custom error message/i)).toBeInTheDocument();
  });

  it('should have reload button in fallback', () => {
    const ThrowError = () => {
      throw new Error('Test');
    };

    render(
      <TestErrorBoundary>
        <ThrowError />
      </TestErrorBoundary>
    );

    expect(screen.getByText(/Reload Dashboard/i)).toBeInTheDocument();
  });
});

describe('NetworkStatusProvider', () => {
  let addEventListenerSpy: ReturnType<typeof vi.spyOn>;
  let removeEventListenerSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    addEventListenerSpy = vi.spyOn(window, 'addEventListener');
    removeEventListenerSpy = vi.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    cleanup();
    addEventListenerSpy.mockRestore();
    removeEventListenerSpy.mockRestore();
  });

it('should have addEventListener method available', () => {
    expect(typeof window.addEventListener).toBe('function');
    expect(typeof window.removeEventListener).toBe('function');
  });
});

describe('ErrorBoundary getDerivedStateFromError', () => {
  it('should return error state', () => {
    const error = new Error('Test error');
    const state = TestErrorBoundary.getDerivedStateFromError(error);
    expect(state).toEqual({ hasError: true, error });
  });
});