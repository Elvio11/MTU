import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Sidebar from './Sidebar';

const mockUsePathname = vi.fn(() => '/');

vi.mock('next/navigation', () => ({
  usePathname: () => mockUsePathname(),
}));

vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: { children: React.ReactNode; href: string; [key: string]: unknown }) =>
    <a href={href} {...props}>{children}</a>,
}));

describe('Sidebar', () => {
  it('renders MTUS branding', () => {
    render(<Sidebar />);
    expect(screen.getByText('MTUS')).toBeInTheDocument();
    expect(screen.getByText('Terminal v2.0')).toBeInTheDocument();
  });

  it('renders all 5 nav items', () => {
    render(<Sidebar />);
    expect(screen.getByText('TERMINAL')).toBeInTheDocument();
    expect(screen.getByText('STRATEGY')).toBeInTheDocument();
    expect(screen.getByText('HISTORY')).toBeInTheDocument();
    expect(screen.getByText('ALERTS')).toBeInTheDocument();
    expect(screen.getByText('SETTINGS')).toBeInTheDocument();
  });

  it('highlights the active nav item', () => {
    mockUsePathname.mockReturnValue('/');
    render(<Sidebar />);
    const terminalLink = screen.getByText('TERMINAL').closest('a');
    expect(terminalLink?.className).toContain('bg-mtus-accent/10');
  });

  it('shows network status', () => {
    render(<Sidebar />);
    expect(screen.getByText('Network Status')).toBeInTheDocument();
    expect(screen.getByText('SOLANA Mainnet')).toBeInTheDocument();
    expect(screen.getByText('Online')).toBeInTheDocument();
  });

  it('works with different active path', () => {
    mockUsePathname.mockReturnValue('/settings');
    render(<Sidebar />);
    const settingsLink = screen.getByText('SETTINGS').closest('a');
    const terminalLink = screen.getByText('TERMINAL').closest('a');
    expect(settingsLink?.className).toContain('bg-mtus-accent/10');
    expect(terminalLink?.className).not.toContain('bg-mtus-accent/10');
  });
});
