import { isOperationalWindowActive } from '../../src/typescript/shared/operational-window';
import { DateTime } from 'luxon';

jest.mock('luxon', () => ({
  DateTime: {
    utc: jest.fn(),
  },
}));

describe('Operational Window Checker', () => {
  it('should return true when IST time is 21:00', () => {
    const mockNow = DateTime.utc();
    mockNow.setZone.mockReturnValue({ hour: 21 });
    (DateTime.utc as jest.Mock).mockReturnValue(mockNow);
    expect(isOperationalWindowActive()).toBe(true);
  });

  it('should return false when IST time is 07:00', () => {
    const mockNow = DateTime.utc();
    mockNow.setZone.mockReturnValue({ hour: 7 });
    (DateTime.utc as jest.Mock).mockReturnValue(mockNow);
    expect(isOperationalWindowActive()).toBe(false);
  });
});
