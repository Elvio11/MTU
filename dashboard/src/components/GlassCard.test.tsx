import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { GlassCard } from './GlassCard';

describe('GlassCard', () => {
  it('renders children', () => {
    render(<GlassCard>Test Content</GlassCard>);
    expect(screen.getByText('Test Content')).toBeInTheDocument();
  });

  it('renders with title', () => {
    render(<GlassCard title="Card Title">Content</GlassCard>);
    expect(screen.getByText('Card Title')).toBeInTheDocument();
  });

  it('renders with subtitle', () => {
    render(<GlassCard subtitle="Card Subtitle">Content</GlassCard>);
    expect(screen.getByText('Card Subtitle')).toBeInTheDocument();
  });

  it('renders with icon', () => {
    const MockIcon = vi.fn(() => <svg data-testid="mock-icon" />);
    render(<GlassCard icon={MockIcon}>Content</GlassCard>);
    expect(screen.getByTestId('mock-icon')).toBeInTheDocument();
  });

  it('renders without title, subtitle, or icon (no header)', () => {
    const { container } = render(<GlassCard>Content</GlassCard>);
    const headers = container.querySelectorAll('.border-b');
    expect(headers).toHaveLength(0);
  });

  it('applies custom className', () => {
    const { container } = render(<GlassCard className="custom-class">Content</GlassCard>);
    const card = container.firstChild as HTMLElement;
    expect(card.className).toContain('custom-class');
  });
});
