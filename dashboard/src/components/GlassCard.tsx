import React from 'react';

interface GlassCardProps {
  children: React.ReactNode;
  className?: string;
  title?: string;
  subtitle?: string;
  icon?: React.ElementType;
}

export const GlassCard: React.FC<GlassCardProps> = ({ 
  children, 
  className = '', 
  title, 
  subtitle, 
  icon: Icon 
}) => {
  return (
    <div className={`bg-mtus-card backdrop-blur-md border border-white/10 rounded-2xl overflow-hidden shadow-2xl transition-all hover:border-white/20 ${className}`}>
      {(title || subtitle || Icon) && (
        <div className="px-6 py-4 border-b border-white/10 flex items-center justify-between">
          <div>
            {title && <h3 className="text-sm font-bold font-heading text-muted uppercase tracking-wider">{title}</h3>}
            {subtitle && <p className="text-[10px] text-muted/60 font-bold uppercase mt-0.5">{subtitle}</p>}
          </div>
          {Icon && <Icon className="text-mtus-accent/50" size={20} />}
        </div>
      )}
      <div className="p-6">
        {children}
      </div>
    </div>
  );
};
