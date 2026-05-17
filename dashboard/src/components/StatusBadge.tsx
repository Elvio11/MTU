import React from 'react';

interface StatusBadgeProps {
  status: 'healthy' | 'unhealthy' | 'online' | 'offline' | 'active' | 'warning' | 'error' | 'success';
  className?: string;
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, className = '' }) => {
  const getColors = () => {
    switch (status) {
      case 'healthy':
      case 'online':
      case 'active':
      case 'success':
        return 'bg-profit/10 text-profit border-profit/20';
      case 'unhealthy':
      case 'offline':
      case 'error':
        return 'bg-loss/10 text-loss border-loss/20';
      case 'warning':
        return 'bg-warning/10 text-warning border-warning/20';
      default:
        return 'bg-white/5 text-muted border-white/10';
    }
  };

  return (
    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-tighter border ${getColors()} ${className}`}>
      {status}
    </span>
  );
};
