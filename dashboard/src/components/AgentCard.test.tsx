import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';
import AgentCard from './AgentCard';

const baseAgent = {
  id: 'agent-1',
  name: 'Test Agent',
  status: 'healthy' as const,
  lastHeartbeat: '2026-05-15 10:30:00',
};

describe('AgentCard', () => {
  it('renders agent name and ID', () => {
    render(<AgentCard agent={baseAgent} />);
    expect(screen.getByText('Test Agent')).toBeInTheDocument();
    expect(screen.getByText('ID: agent-1')).toBeInTheDocument();
  });

  it('renders healthy status correctly', () => {
    render(<AgentCard agent={baseAgent} />);
    expect(screen.getByText('healthy')).toBeInTheDocument();
  });

  it('renders unhealthy status correctly', () => {
    render(<AgentCard agent={{ ...baseAgent, status: 'unhealthy' }} />);
    expect(screen.getByText('unhealthy')).toBeInTheDocument();
  });

  it('renders starting/paused status correctly', () => {
    render(<AgentCard agent={{ ...baseAgent, status: 'starting' }} />);
    expect(screen.getByText('starting')).toBeInTheDocument();
    render(<AgentCard agent={{ ...baseAgent, status: 'paused' }} />);
    expect(screen.getByText('paused')).toBeInTheDocument();
  });

  it('shows Messages label', () => {
    render(<AgentCard agent={baseAgent} />);
    expect(screen.getByText('Messages')).toBeInTheDocument();
  });

  it('shows Errors label', () => {
    render(<AgentCard agent={baseAgent} />);
    expect(screen.getByText('Errors')).toBeInTheDocument();
  });

  it('shows lastHeartbeat time', () => {
    render(<AgentCard agent={baseAgent} />);
    expect(screen.getByText('2026-05-15 10:30:00')).toBeInTheDocument();
  });

  it('renders with errors count', () => {
    render(<AgentCard agent={{ ...baseAgent, errors: 5 }} />);
    expect(screen.getByText('5')).toBeInTheDocument();
  });
});
