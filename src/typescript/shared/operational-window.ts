import { DateTime } from 'luxon';
import * as fs from 'fs';
import * as yaml from 'js-yaml';
import * as path from 'path';

export const isOperationalWindowActive = (): boolean => {
  let start = 0;
  let end = 24;

  try {
    const configPath = path.join(process.cwd(), 'config', 'config.yaml');
    const fileContents = fs.readFileSync(configPath, 'utf8');
    const config = yaml.load(fileContents) as any;
    
    if (config?.system?.operational_window) {
      start = config.system.operational_window.start_hour_ist ?? 0;
      end = config.system.operational_window.end_hour_ist ?? 24;
    }
  } catch (e) {
    console.warn('[OperationalWindow] Failed to load config, defaulting to 24/7');
  }

  const now = DateTime.utc();
  const istTime = now.setZone('Asia/Kolkata');
  const currentHour = istTime.hour;

  if (start === end) {
    return true; // 24/7
  }

  if (start === 0 && end === 24) {
    return true;
  }

  if (start > end) {
    // Over-midnight window (e.g. 21:00 to 06:00)
    return currentHour >= start || currentHour < end;
  } else {
    // Standard window (e.g. 09:00 to 17:00)
    return currentHour >= start && currentHour < end;
  }
};
