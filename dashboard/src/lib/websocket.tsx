"use client";

import React, { createContext, useContext, useEffect, useState, useRef, ReactNode } from 'react';

export interface WebSocketMessagePayload {
  type: string;
  payload: unknown;
}

export interface WebSocketContextType {
  subscribe: (type: string, callback: (payload: unknown) => void) => void;
  unsubscribe: (type: string, callback: (payload: unknown) => void) => void;
  send: (data: unknown) => void;
  connected: boolean;
  reconnecting: boolean;
  lastMessage: WebSocketMessagePayload | null;
  setAuthToken: (token: string | null) => void;
}

const WebSocketContext = createContext<WebSocketContextType | null>(null);

export class MTUSWebSocket {
  private ws: WebSocket | null = null;
  private listeners: Map<string, Array<(payload: unknown) => void>> = new Map();
  private url: string;
  private authToken: string | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private baseReconnectDelay = 1000;
  private maxReconnectDelay = 30000;
  private connected = false;
  private lastMessage: WebSocketMessagePayload | null = null;
  private onStateChange: ((connected: boolean, reconnecting: boolean) => void) | null = null;

  constructor(url?: string) {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL;
    this.url = wsUrl || url || 'ws://localhost:4001';
  }

  setAuthToken(token: string | null) {
    this.authToken = token;
    if (this.connected && token) {
      this.send({ type: 'auth', token });
    }
  }

  setStateChangeCallback(callback: (connected: boolean, reconnecting: boolean) => void) {
    this.onStateChange = callback;
  }

  private getReconnectDelay(): number {
    const delay = this.baseReconnectDelay * Math.pow(2, this.reconnectAttempts);
    const jitter = Math.random() * 1000;
    return Math.min(delay + jitter, this.maxReconnectDelay);
  }

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return;
    
    console.log('[WS] Attempting to connect to:', this.url);
    const isReconnecting = this.reconnectAttempts > 0;
    if (this.onStateChange) {
      this.onStateChange(false, isReconnecting);
    }
    
    try {
      this.ws = new WebSocket(this.url);
      
      this.ws.onopen = () => {
        console.log('[WS] Connected!');
        this.connected = true;
        this.reconnectAttempts = 0;
        if (process.env.NODE_ENV === 'development') {
          console.log('Dashboard WebSocket connected');
        }
        if (this.authToken) {
          this.send({ type: 'auth', token: this.authToken });
        }
        if (this.onStateChange) {
          this.onStateChange(true, false);
        }
      };
      
      this.ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string) as WebSocketMessagePayload;
          this.lastMessage = data;
          this.notifyListeners(data.type, data.payload);
        } catch (e) { 
          if (process.env.NODE_ENV === 'development') {
            console.error('WS message error:', e); 
          }
        }
      };
      
      this.ws.onerror = (error) => {
        console.error('[WS] Error:', error);
      };
      
      this.ws.onclose = () => {
        this.connected = false;
        this.reconnectAttempts++;
        
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          const delay = this.getReconnectDelay();
          if (process.env.NODE_ENV === 'development') {
            console.log(`WS: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
          }
          
          if (this.onStateChange) {
            this.onStateChange(false, true);
          }
          
          this.reconnectTimer = setTimeout(() => this.connect(), delay);
        } else {
          if (process.env.NODE_ENV === 'development') {
            console.log('WS: Max reconnect attempts reached');
          }
          if (this.onStateChange) {
            this.onStateChange(false, false);
          }
        }
        this.ws = null;
      };
      
      this.ws.onerror = () => {
        this.reconnectAttempts++;
      };
    } catch (e) { 
      if (process.env.NODE_ENV === 'development') {
        console.error('WS connection error:', e); 
      }
      this.reconnectAttempts++;
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = this.getReconnectDelay();
        this.reconnectTimer = setTimeout(() => this.connect(), delay);
      }
    }
  }

  subscribe(type: string, callback: (payload: unknown) => void) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type)!.push(callback);
  }

  unsubscribe(type: string, callback: (payload: unknown) => void) {
    const handlers = this.listeners.get(type);
    if (handlers) {
      const idx = handlers.indexOf(callback);
      if (idx > -1) handlers.splice(idx, 1);
    }
  }

  private notifyListeners(type: string, payload: unknown) {
    const handlers = this.listeners.get(type);
    if (handlers) handlers.forEach(h => h(payload));
  }

  send(data: unknown) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    }
  }

  disconnect() {
    this.reconnectAttempts = this.maxReconnectAttempts;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    if (this.ws) { this.ws.close(); this.ws = null; }
    this.connected = false;
    if (this.onStateChange) {
      this.onStateChange(false, false);
    }
  }

  isConnected(): boolean {
    return this.connected && this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }

  getLastMessage(): WebSocketMessagePayload | null {
    return this.lastMessage;
  }
}

const wsInstance = typeof window !== 'undefined' ? new MTUSWebSocket() : null;

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessagePayload | null>(null);
  const wsRef = useRef<MTUSWebSocket | null>(wsInstance);

  useEffect(() => {
    const ws = wsRef.current;
    if (ws) {
      ws.setStateChangeCallback((conn, reconn) => {
        console.log('[WS] State changed:', conn, reconn);
        setConnected(conn);
        setReconnecting(reconn);
      });
      console.log('[WS] Calling connect...');
      ws.connect();
      const intervalId = setInterval(() => {
        setConnected(ws.isConnected());
        const lastMsg = ws.getLastMessage();
        if (lastMsg) setLastMessage(lastMsg);
      }, 1000);
      return () => {
        clearInterval(intervalId);
        ws.disconnect();
      };
    }
    return () => {};
  }, []);

  const contextValue: WebSocketContextType = {
    subscribe: (type: string, callback: (payload: unknown) => void) => wsRef.current?.subscribe(type, callback),
    unsubscribe: (type: string, callback: (payload: unknown) => void) => wsRef.current?.unsubscribe(type, callback),
    send: (data: unknown) => wsRef.current?.send(data),
    connected,
    reconnecting,
    lastMessage,
    setAuthToken: (token: string | null) => wsRef.current?.setAuthToken(token),
  };

  return (
    <WebSocketContext.Provider value={contextValue}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket(): WebSocketContextType | null {
  return useContext(WebSocketContext);
}