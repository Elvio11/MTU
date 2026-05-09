import * as crypto from 'crypto';

export const generateOTP = (seed: string, timestamp?: number): string => {
  const ts = timestamp || Math.floor(Date.now() / 1000);
  const message = Math.floor(ts / 30).toString();
  return crypto.createHmac('sha256', seed).update(message).digest('hex').substring(0, 8);
};

export const verifyOTP = (seed: string, otp: string, window: number = 1): boolean => {
  const currentTs = Math.floor(Date.now() / 1000);
  const currentWindow = Math.floor(currentTs / 30);
  for (let delta = -window; delta <= window; delta++) {
    const testWindow = currentWindow + delta;
    const testOtp = crypto.createHmac('sha256', seed).update(testWindow.toString()).digest('hex').substring(0, 8);
    if (crypto.timingSafeEqual(Buffer.from(testOtp, 'hex'), Buffer.from(otp, 'hex'))) {
      return true;
    }
  }
  return false;
};
