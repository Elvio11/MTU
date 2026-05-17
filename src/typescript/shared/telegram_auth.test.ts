import { generateOTP, verifyOTP } from './telegram_auth';

describe('telegram_auth', () => {
  test('generateOTP produces consistent results', () => {
    const otp1 = generateOTP('test-seed', 1000000);
    const otp2 = generateOTP('test-seed', 1000000);
    expect(otp1).toBe(otp2);
    expect(otp1).toHaveLength(8);
  });

  test('verifyOTP validates correct OTP', () => {
    const otp = generateOTP('seed');
    expect(verifyOTP('seed', otp, 1)).toBe(true);
  });

  test('verifyOTP rejects wrong OTP', () => {
    expect(verifyOTP('seed', '00000000', 0)).toBe(false);
  });

  test('verifyOTP with window accepts nearby', () => {
    const pastTs = Math.floor(Date.now() / 1000) - 30;
    const otp = generateOTP('seed', pastTs);
    expect(verifyOTP('seed', otp, 1)).toBe(true);
  });
});
