/**
 * Mock Redis for local testing when Redis isn't available
 * Simple in-memory pub/sub - for development/testing only
 */

import { EventEmitter } from 'events';

// Singleton store for cross-instance communication
export class MockRedisStore {
  private static instance: MockRedisStore;
  private data: Map<string, string> = new Map();
  private channelCallbacks: Map<string, Set<(msg: string) => void>> = new Map();
  private emitter: EventEmitter = new EventEmitter();
  
  static getInstance(): MockRedisStore {
    if (!MockRedisStore.instance) {
      MockRedisStore.instance = new MockRedisStore();
    }
    return MockRedisStore.instance;
  }
  
  reset(): void {
    this.data.clear();
    this.channelCallbacks.clear();
    this.emitter.removeAllListeners();
  }
  
  get(key: string): string | null {
    return this.data.get(key) || null;
  }
  
  set(key: string, value: string): void {
    this.data.set(key, value);
  }
  
  subscribe(channel: string, callback: (msg: string) => void): void {
    if (!this.channelCallbacks.has(channel)) {
      this.channelCallbacks.set(channel, new Set());
    }
    this.channelCallbacks.get(channel)!.add(callback);
  }
  
  unsubscribe(channel: string, callback: (msg: string) => void): void {
    const callbacks = this.channelCallbacks.get(channel);
    if (callbacks) {
      callbacks.delete(callback);
    }
  }
  
  publish(channel: string, message: string): void {
    console.log(`[MockRedis] Publishing to ${channel}: ${message.substring(0, 60)}...`);
    
    // Emit to EventEmitter for subscribers
    this.emitter.emit('message', channel, message);
    
    // Call stored callbacks for this channel
    const callbacks = this.channelCallbacks.get(channel);
    if (callbacks) {
      callbacks.forEach((cb) => {
        try {
          cb(message);
        } catch (e) {
          console.error(`[MockRedis] Callback error:`, e);
        }
      });
    }
  }
  
  onMessage(callback: (channel: string, message: string) => void): void {
    this.emitter.on('message', callback);
  }
  
  offMessage(callback: (channel: string, message: string) => void): void {
    this.emitter.off('message', callback);
  }
}

class MockRedis extends EventEmitter {
  private store: MockRedisStore;
  private subscribedChannels: Map<string, (msg: string) => void> = new Map();
  
  constructor() {
    super();
    this.store = MockRedisStore.getInstance();
  }
  
  async connect(): Promise<void> {
    console.log('[MockRedis] Connected (in-memory)');
  }
  
  async ping(): Promise<string> {
    return 'PONG';
  }
  
  async get(key: string): Promise<string | null> {
    return this.store.get(key);
  }
  
  async set(key: string, value: string): Promise<void> {
    this.store.set(key, value);
  }
  
  async publish(channel: string, message: string): Promise<void> {
    this.store.publish(channel, message);
  }
  
  async subscribe(channel: string, callback: (msg: string) => void): Promise<void> {
    console.log(`[MockRedis] Subscribed to ${channel}`);
    this.subscribedChannels.set(channel, callback);
    this.store.subscribe(channel, callback);
  }
  
  duplicate(): MockRedis {
    const mock = new MockRedis();
    // Copy subscriptions to new instance
    this.subscribedChannels.forEach((cb, channel) => {
      mock.store.subscribe(channel, cb);
    });
    return mock;
  }
  
  async quit(): Promise<void> {
    // Remove all subscriptions from the shared store
    this.subscribedChannels.forEach((cb, channel) => {
      this.store.unsubscribe(channel, cb);
    });
    this.subscribedChannels.clear();
    console.log('[MockRedis] Disconnected');
  }
}

export default MockRedis;

export function resetMockRedis(): void {
  MockRedisStore.getInstance().reset();
}