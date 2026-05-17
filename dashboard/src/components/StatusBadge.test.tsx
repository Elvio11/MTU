import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { StatusBadge } from './StatusBadge';

describe('StatusBadge', () => {
  it('renders with healthy status', () => {
    const { container } = render(<StatusBadge status="healthy" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-profit');
  });

  it('renders with unhealthy status', () => {
    const { container } = render(<StatusBadge status="unhealthy" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-loss');
  });

  it('renders with online status', () => {
    const { container } = render(<StatusBadge status="online" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-profit');
  });

  it('renders with offline status', () => {
    const { container } = render(<StatusBadge status="offline" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-loss');
  });

  it('renders with active status', () => {
    const { container } = render(<StatusBadge status="active" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-profit');
  });

  it('renders with warning status', () => {
    const { container } = render(<StatusBadge status="warning" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-warning');
  });

  it('renders with error status', () => {
    const { container } = render(<StatusBadge status="error" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-loss');
  });

  it('renders with success status', () => {
    const { container } = render(<StatusBadge status="success" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-profit');
  });

  it('applies custom className', () => {
    const { container } = render(<StatusBadge status="healthy" className="my-custom-class" />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('my-custom-class');
  });

  it('displays the status text', () => {
    render(<StatusBadge status="healthy" />);
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('renders with unknown status using default styling', () => {
    const { container } = render(<StatusBadge status={'unknown' as any} />);
    const span = container.firstChild as HTMLElement;
    expect(span.className).toContain('text-muted');
  });
});
