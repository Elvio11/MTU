module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src/typescript'],
  testMatch: ['**/*.test.ts'],
  moduleFileExtensions: ['ts', 'js', 'json'],
  collectCoverageFrom: [
    'src/typescript/**/*.ts',
    '!src/typescript/**/*.d.ts'
  ],
  coverageDirectory: 'coverage',
  verbose: true
};