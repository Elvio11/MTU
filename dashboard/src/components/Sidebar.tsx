'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { 
  History, 
  Settings, 
  Terminal,
  Activity,
  Layers,
  Zap,
  ShieldAlert
} from 'lucide-react';

const navItems = [
  { name: 'TERMINAL', href: '/', icon: Terminal },
  { name: 'STRATEGY', href: '/strategy', icon: Layers },
  { name: 'HISTORY', href: '/history', icon: History },
  { name: 'ALERTS', href: '/alerts', icon: ShieldAlert },
  { name: 'SETTINGS', href: '/settings', icon: Settings },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="w-64 bg-mtus-card/50 backdrop-blur-xl border-r border-white/10 flex flex-col h-screen sticky top-0">
      <div className="p-8">
        <Link href="/" className="flex items-center gap-3 group">
          <div className="w-10 h-10 bg-gradient-to-br from-mtus-accent to-mtus-secondary rounded-xl flex items-center justify-center shadow-[0_0_20px_rgba(245,158,11,0.3)] group-hover:scale-110 transition-transform">
            <Zap className="text-white fill-white" size={20} />
          </div>
          <div>
            <span className="text-xl font-bold font-heading text-white tracking-widest">MTUS</span>
            <div className="text-[10px] text-mtus-accent font-bold tracking-[0.2em] -mt-1 opacity-80 uppercase">Terminal v2.0</div>
          </div>
        </Link>
      </div>

      <nav className="flex-1 px-4 space-y-1">
        {navItems.map((item) => {
          const active = pathname === item.href;
          
          return (
            <Link
              key={item.name}
              href={item.href}
              className={`flex items-center gap-4 px-4 py-3 rounded-xl transition-all group ${
                active 
                  ? 'bg-mtus-accent/10 text-mtus-accent border border-mtus-accent/20' 
                  : 'text-muted hover:text-white hover:bg-white/5 border border-transparent'
              }`}
            >
              <item.icon size={20} className={active ? 'text-mtus-accent' : 'text-muted group-hover:text-white'} />
              <span className={`text-xs font-bold tracking-widest ${active ? 'text-white' : ''}`}>{item.name}</span>
              {active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-mtus-accent shadow-[0_0_8px_rgba(245,158,11,0.8)]" />}
            </Link>
          );
        })}
      </nav>

      <div className="p-6">
        <div className="bg-white/5 border border-white/10 rounded-2xl p-4">
          <div className="flex items-center gap-3 mb-3">
            <Activity className="text-profit" size={16} />
            <span className="text-[10px] font-bold text-white uppercase tracking-wider">Network Status</span>
          </div>
          <div className="space-y-2">
            <div className="flex justify-between items-center text-[10px]">
              <span className="text-muted">SOLANA Mainnet</span>
              <span className="text-profit">Online</span>
            </div>
            <div className="w-full bg-white/5 h-1 rounded-full overflow-hidden">
              <div className="bg-profit w-[98%] h-full animate-pulse" />
            </div>
          </div>
        </div>
      </div>
    </aside>
  );
}