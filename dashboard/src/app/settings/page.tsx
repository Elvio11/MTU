'use client';

import { useState } from 'react';
import { useWebSocket } from '@/lib/websocket';
import { useTheme } from '@/lib/theme-context';
import { useAdmin } from '@/lib/admin-context';
import { Settings, Wifi, RefreshCw, Save, MessageCircle, Bell, Shield, Key, CheckCircle, XCircle, Loader2, Sun, Moon, Monitor, Lock, Unlock } from 'lucide-react';

interface TelegramConfig {
  botToken: string;
  adminChatId: string;
  enabled: boolean;
  notifications: {
    trades: boolean;
    positions: boolean;
    agents: boolean;
    errors: boolean;
    alerts: boolean;
  };
}

const DEFAULT_CONFIG: TelegramConfig = {
  botToken: '',
  adminChatId: '',
  enabled: false,
  notifications: {
    trades: true,
    positions: true,
    agents: true,
    errors: true,
    alerts: true,
  },
};

export default function SettingsPage() {
  const [wsUrl, setWsUrl] = useState(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem('mtus_ws_url') || 'ws://localhost:3001';
    }
    return 'ws://localhost:3001';
  });
  const [saved, setSaved] = useState(false);
  const [isReloading, setIsReloading] = useState(false);
  const [testingBot, setTestingBot] = useState(false);
  const [botStatus, setBotStatus] = useState<'unknown' | 'connected' | 'error'>('unknown');
  const ws = useWebSocket();
  const { theme, setTheme } = useTheme();
  const { isAdmin, isAdminMode, enableAdmin, disableAdmin } = useAdmin();
  const [otpInput, setOtpInput] = useState('');
  const [otpError, setOtpError] = useState('');

  const [telegramConfig, setTelegramConfig] = useState<TelegramConfig>(() => {
    if (typeof window !== 'undefined') {
      const stored = localStorage.getItem('mtus_telegram_config');
      return stored ? JSON.parse(stored) : DEFAULT_CONFIG;
    }
    return DEFAULT_CONFIG;
  });

  const handleSave = () => {
    localStorage.setItem('mtus_ws_url', wsUrl);
    localStorage.setItem('mtus_telegram_config', JSON.stringify(telegramConfig));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const handleReload = () => {
    setIsReloading(true);
    window.location.reload();
  };

  const testTelegramBot = async () => {
    setTestingBot(true);
    setBotStatus('unknown');
    
    try {
      const response = await fetch(`https://api.telegram.org/bot${telegramConfig.botToken}/getMe`);
      if (response.ok) {
        setBotStatus('connected');
      } else {
        setBotStatus('error');
      }
    } catch {
      setBotStatus('error');
    }
    
    setTestingBot(false);
  };

  const toggleNotification = (key: keyof TelegramConfig['notifications']) => {
    setTelegramConfig(prev => ({
      ...prev,
      notifications: {
        ...prev.notifications,
        [key]: !prev.notifications[key],
      },
    }));
  };

  return (
    <div className="max-w-3xl space-y-6">
      <h1 className="text-2xl font-bold text-white">Settings</h1>

      {/* WebSocket Configuration */}
      <div className="bg-mtus-card p-6 rounded-xl border border-slate-700 space-y-4">
        <div className="flex items-center gap-3">
          <Settings className="text-mtus-accent" size={20} />
          <h2 className="text-lg font-semibold text-white">WebSocket Configuration</h2>
        </div>

        <div>
          <label className="block text-sm text-slate-400 mb-2">WebSocket URL</label>
          <input
            type="text"
            value={wsUrl}
            onChange={(e) => setWsUrl(e.target.value)}
            className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white focus:border-mtus-accent focus:outline-none"
            placeholder="ws://localhost:3001"
          />
        </div>

        <div className="flex gap-3">
          <button
            onClick={handleSave}
            className="flex items-center gap-2 px-4 py-2 bg-mtus-accent hover:bg-blue-600 rounded-lg text-sm font-medium transition-colors"
          >
            <Save size={16} />
            Save
          </button>
          <button
            onClick={handleReload}
            className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors"
          >
            <RefreshCw size={16} />
            Reload Page
          </button>
          {saved && (
            <span className="flex items-center text-profit text-sm">Settings saved!</span>
          )}
        </div>
      </div>

      {/* Admin Mode */}
      <div className="bg-mtus-card p-6 rounded-xl border border-slate-700 space-y-4">
        <div className="flex items-center gap-3">
          <Shield className="text-mtus-accent" size={20} />
          <h2 className="text-lg font-semibold text-white">Admin Mode</h2>
          <span className={`ml-auto px-2 py-1 rounded text-xs ${isAdminMode ? 'bg-profit/20 text-profit' : 'bg-slate-700 text-slate-400'}`}>
            {isAdminMode ? 'Active' : 'Inactive'}
          </span>
        </div>

        {!isAdminMode ? (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">Enter OTP to enable admin controls (killswitch, pause, etc.)</p>
            <div className="flex gap-2">
              <input
                type="password"
                value={otpInput}
                onChange={(e) => { setOtpInput(e.target.value); setOtpError(''); }}
                placeholder="Enter OTP"
                className="flex-1 px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white focus:border-mtus-accent focus:outline-none"
              />
              <button
                onClick={() => {
                  if (enableAdmin(otpInput)) {
                    setOtpInput('');
                  } else {
                    setOtpError('Invalid OTP');
                  }
                }}
                className="flex items-center gap-2 px-4 py-2 bg-mtus-accent hover:bg-blue-600 rounded-lg text-sm font-medium transition-colors"
              >
                <Lock size={16} />
                Enable
              </button>
            </div>
            {otpError && <p className="text-loss text-sm">{otpError}</p>}
          </div>
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-400">Admin mode is active. Protected actions require confirmation.</p>
            <button
              onClick={disableAdmin}
              className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors"
            >
              <Unlock size={16} />
              Disable Admin Mode
            </button>
          </div>
        )}
      </div>

      {/* Connection Status */}
      <div className="bg-mtus-card p-6 rounded-xl border border-slate-700 space-y-4">
        <div className="flex items-center gap-3">
          <Wifi className="text-mtus-accent" size={20} />
          <h2 className="text-lg font-semibold text-white">Connection Status</h2>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div className="flex items-center gap-3 p-3 bg-slate-800 rounded-lg">
            <div className={`w-3 h-3 rounded-full ${ws?.connected ? 'bg-profit' : 'bg-loss'}`} />
            <div>
              <p className="text-sm text-slate-400">WebSocket</p>
              <p className="text-white font-medium">{ws?.connected ? 'Connected' : 'Disconnected'}</p>
            </div>
          </div>
          <div className="flex items-center gap-3 p-3 bg-slate-800 rounded-lg">
            <div className={`w-3 h-3 rounded-full ${botStatus === 'connected' ? 'bg-profit' : botStatus === 'error' ? 'bg-loss' : 'bg-muted'}`} />
            <div>
              <p className="text-sm text-slate-400">Telegram Bot</p>
              <p className="text-white font-medium">
                {botStatus === 'connected' ? 'Connected' : botStatus === 'error' ? 'Error' : 'Not tested'}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Theme Settings */}
      <div className="bg-mtus-card p-6 rounded-xl border border-slate-700 space-y-4">
        <div className="flex items-center gap-3">
          <Sun className="text-mtus-accent" size={20} />
          <h2 className="text-lg font-semibold text-white">Appearance</h2>
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => setTheme('dark')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              theme === 'dark' ? 'bg-mtus-accent text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            <Moon size={16} />
            Dark
          </button>
          <button
            onClick={() => setTheme('light')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              theme === 'light' ? 'bg-mtus-accent text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            <Sun size={16} />
            Light
          </button>
          <button
            onClick={() => setTheme('system')}
            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              theme === 'system' ? 'bg-mtus-accent text-white' : 'bg-slate-700 text-slate-400 hover:bg-slate-600'
            }`}
          >
            <Monitor size={16} />
            System
          </button>
        </div>
      </div>

      {/* Telegram Bot Configuration */}
      <div className="bg-mtus-card p-6 rounded-xl border border-slate-700 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <MessageCircle className="text-mtus-accent" size={20} />
            <h2 className="text-lg font-semibold text-white">Telegram Bot</h2>
          </div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={telegramConfig.enabled}
              onChange={(e) => setTelegramConfig(prev => ({ ...prev, enabled: e.target.checked }))}
              className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-mtus-accent focus:ring-mtus-accent"
            />
            <span className="text-sm text-slate-400">Enable</span>
          </label>
        </div>

        {telegramConfig.enabled && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="flex items-center gap-2 text-sm text-slate-400 mb-2">
                  <Key size={14} />
                  Bot Token
                </label>
                <input
                  type="password"
                  value={telegramConfig.botToken}
                  onChange={(e) => setTelegramConfig(prev => ({ ...prev, botToken: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white focus:border-mtus-accent focus:outline-none"
                  placeholder="1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
                />
                <p className="text-xs text-slate-500 mt-1">Get from @BotFather on Telegram</p>
              </div>
              <div>
                <label className="flex items-center gap-2 text-sm text-slate-400 mb-2">
                  <Shield size={14} />
                  Admin Chat ID
                </label>
                <input
                  type="text"
                  value={telegramConfig.adminChatId}
                  onChange={(e) => setTelegramConfig(prev => ({ ...prev, adminChatId: e.target.value }))}
                  className="w-full px-4 py-2.5 bg-slate-800 border border-slate-600 rounded-lg text-white focus:border-mtus-accent focus:outline-none"
                  placeholder="123456789"
                />
                <p className="text-xs text-slate-500 mt-1">Your Telegram chat ID</p>
              </div>
            </div>

            <div className="flex gap-3">
              <button
                onClick={testTelegramBot}
                disabled={!telegramConfig.botToken || testingBot}
                className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 rounded-lg text-sm font-medium transition-colors disabled:opacity-50"
              >
                {testingBot ? <Loader2 size={16} /> : <CheckCircle size={16} />}
                Test Connection
              </button>
            </div>

            {botStatus === 'connected' && (
              <div className="flex items-center gap-2 text-profit text-sm">
                <CheckCircle size={16} />
                Bot connected successfully!
              </div>
            )}
            {botStatus === 'error' && (
              <div className="flex items-center gap-2 text-loss text-sm">
                <XCircle size={16} />
                Failed to connect. Check your token.
              </div>
            )}
          </>
        )}
      </div>

      {/* Notification Settings */}
      {telegramConfig.enabled && (
        <div className="bg-mtus-card p-6 rounded-xl border border-slate-700 space-y-4">
          <div className="flex items-center gap-3">
            <Bell className="text-mtus-accent" size={20} />
            <h2 className="text-lg font-semibold text-white">Notification Preferences</h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {Object.entries(telegramConfig.notifications).map(([key, value]) => (
              <label
                key={key}
                className="flex items-center justify-between p-3 bg-slate-800 rounded-lg cursor-pointer hover:bg-slate-700 transition-colors"
              >
                <span className="text-sm text-white capitalize">{key} Notifications</span>
                <input
                  type="checkbox"
                  checked={value}
                  onChange={() => toggleNotification(key as keyof TelegramConfig['notifications'])}
                  className="w-4 h-4 rounded bg-slate-700 border-slate-600 text-mtus-accent focus:ring-mtus-accent"
                />
              </label>
            ))}
          </div>
        </div>
      )}

      {/* System Info */}
      <div className="bg-mtus-card p-6 rounded-xl border border-slate-700">
        <h2 className="text-lg font-semibold text-white mb-4">System Info</h2>
        <div className="grid grid-cols-2 gap-4 text-sm">
          <div className="flex justify-between p-3 bg-slate-800 rounded-lg">
            <span className="text-slate-400">Dashboard Version</span>
            <span className="text-white">1.0.0</span>
          </div>
          <div className="flex justify-between p-3 bg-slate-800 rounded-lg">
            <span className="text-slate-400">Next.js</span>
            <span className="text-white">16.2.4</span>
          </div>
          <div className="flex justify-between p-3 bg-slate-800 rounded-lg">
            <span className="text-slate-400">React</span>
            <span className="text-white">19.2.4</span>
          </div>
          <div className="flex justify-between p-3 bg-slate-800 rounded-lg">
            <span className="text-slate-400">Data Source</span>
            <span className="text-white">Binance WS</span>
          </div>
        </div>
      </div>
    </div>
  );
}