/**
 * Config Validator - Validates config.yaml against JSON Schema
 * Section 6.1: Startup validates config against schema
 */

import * as fs from 'fs';
import * as path from 'path';
import * as Ajv from 'ajv';
import * as yaml from 'js-yaml';

const SCHEMA_PATH = path.join(process.cwd(), 'config', 'config.schema.json');

let ajvInstance: Ajv.Ajv | null = null;

function getAjv(): Ajv.Ajv {
  if (!ajvInstance) {
    ajvInstance = new Ajv.default({ allErrors: true });
  }
  return ajvInstance;
}

interface ValidationResult {
  isValid: boolean;
  errors?: string[];
}

/**
 * Load and parse the JSON schema
 */
function loadSchema(): any {
  try {
    const schemaPath = path.resolve(SCHEMA_PATH);
    if (!fs.existsSync(schemaPath)) {
      return { error: `Schema file not found: ${schemaPath}` };
    }
    const schemaContent = fs.readFileSync(schemaPath, 'utf-8');
    return JSON.parse(schemaContent);
  } catch (e: any) {
    return { error: `Failed to load schema: ${e.message}` };
  }
}

/**
 * Validate config object against schema
 */
export function validateConfig(config: any): ValidationResult {
  const schemaOrError = loadSchema();
  if (schemaOrError.error) {
    return { isValid: false, errors: [schemaOrError.error] };
  }

  try {
    const ajv = getAjv();
    const validate = ajv.compile(schemaOrError);
    const valid = validate(config);

    if (!valid) {
      const errors = validate.errors?.map(
        (err) => `${err.message} (path: ${err.instancePath || '/'})`
      ) || ['Unknown validation error'];
      return { isValid: false, errors };
    }

    return { isValid: true };
  } catch (e: any) {
    return { isValid: false, errors: [`Validation error: ${e.message}`] };
  }
}

/**
 * Validate a config file (YAML or JSON)
 */
export function validateConfigFile(configPath: string): ValidationResult {
  try {
    if (!fs.existsSync(configPath)) {
      return { isValid: false, errors: [`Config file not found: ${configPath}`] };
    }

    const content = fs.readFileSync(configPath, 'utf-8');
    let config: any;

    try {
      config = JSON.parse(content);
    } catch {
      config = yaml.load(content);
    }

    return validateConfig(config);
  } catch (e: any) {
    return { isValid: false, errors: [`Failed to parse config: ${e.message}`] };
  }
}

/**
 * Simple YAML parser for basic key-value pairs
 * (avoids adding js-yaml dependency)
 */
export function parseSimpleYaml(yaml: string): any {
  const result: any = {};
  const lines = yaml.split('\n');
  let currentSection: any = result;
  let sectionStack: any[] = [];

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    // Check for section
    const sectionMatch = trimmed.match(/^(\w+):\s*$/);
    if (sectionMatch) {
      const sectionName = sectionMatch[1];
      result[sectionName] = {};
      currentSection = result[sectionName];
      continue;
    }

    // Check for key-value
    const kvMatch = trimmed.match(/^(\w+):\s*(.+)$/);
    if (kvMatch) {
      const key = kvMatch[1];
      let value: any = kvMatch[2].trim();

      // Remove comments
      value = value.split('#')[0].trim();

      // Parse values
      if (value === 'true') value = true;
      else if (value === 'false') value = false;
      else if (!isNaN(Number(value))) value = Number(value);
      else if (value.startsWith('"') && value.endsWith('"')) {
        value = value.slice(1, -1);
      }

      currentSection[key] = value;
    }
  }

  return result;
}

/**
 * Validate config at startup and exit if invalid
 */
export function validateConfigAtStartup(configPath?: string): void {
  const defaultPath = path.join(process.cwd(), 'config', 'config.yaml');
  const configToValidate = configPath || defaultPath;

  console.log(`[CONFIG] Validating ${configToValidate}...`);
  const result = validateConfigFile(configToValidate);

  if (!result.isValid) {
    console.error('[CONFIG] ❌ Configuration validation failed:');
    result.errors?.forEach((err) => console.error(`  - ${err}`));
    process.exit(1);
  }

  console.log('[CONFIG] ✅ Configuration is valid');
}

if (require.main === module) {
  validateConfigAtStartup();
}
