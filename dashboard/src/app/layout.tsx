import type { Metadata } from 'next';
import './globals.css';
import Providers from '@/app/providers';
import Sidebar from '@/components/Sidebar';

export const metadata: Metadata = {
  title: 'MTUS Dashboard | MemeTrader Unified System',
  description: 'Professional trading dashboard for meme coin trading',
  manifest: '/manifest.json',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="bg-mtus-bg" suppressHydrationWarning>
        <Providers>
          <div className="flex min-h-screen">
            <Sidebar />
            <main className="flex-1 p-6 overflow-auto">
              {children}
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}