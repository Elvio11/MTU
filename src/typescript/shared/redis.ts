import Redis from 'ioredis';
import dotenv from 'dotenv';

dotenv.config();

const REDIS_URL = process.env.REDIS_URL || 'redis://localhost:6379';

/**
 * Creates a robust Redis client with connection monitoring and fallback to mock
 */
export async function createRedisClient(): Promise<Redis> {
  try {
    const redis = new Redis(REDIS_URL, { 
      connectTimeout: 5000,
      maxRetriesPerRequest: 1,
      retryStrategy(times) {
        if (times > 3) {
          return null; // Stop retrying after 3 attempts
        }
        return Math.min(times * 100, 3000);
      }
    });

    // Wait for connection with timeout
    await new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('Redis connection timeout')), 3000);
      redis.once('ready', () => {
        clearTimeout(timeout);
        resolve(true);
      });
      redis.once('error', (err) => {
        clearTimeout(timeout);
        reject(err);
      });
    });

    console.log('[Redis] Connected to Redis');
    return redis;
  } catch (e: any) {
    console.log(`[Redis] Connection failed (${e.message}), using mock in-memory fallback`);
    try {
      const MockRedis = require('./mock_redis').default;
      return new MockRedis();
    } catch (err) {
      console.error('[Redis] Failed to load MockRedis, creating minimal fallback');
      // Very basic mock if even loading mock fails
      return {
        on: () => {},
        publish: async () => 0,
        subscribe: async () => {},
        get: async () => null,
        set: async () => 'OK',
        duplicate: () => ({ on: () => {}, subscribe: async () => {} }),
        quit: async () => 'OK',
      } as any;
    }
  }
}
