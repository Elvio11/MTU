# Contributing to MTUS

Thank you for your interest in contributing to the MemeTrader Unified System! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How Can I Contribute](#how-can-i-contribute)
- [Development Setup](#development-setup)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Commit Message Convention](#commit-message-convention)
- [Branch Naming](#branch-naming)

---

## Code of Conduct

- Be respectful and inclusive in all interactions
- Welcome newcomers and help them get oriented
- Focus on what is best for the community and the project
- Show empathy toward other community members
- Accept constructive criticism gracefully

## How Can I Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues. When creating a bug report, include:

- **Clear title and description**
- **Steps to reproduce** the behavior
- **Expected vs actual behavior**
- **Environment details** (OS, Node.js version, Python version, Redis version)
- **Logs or error messages** if available
- **Screenshots** if applicable

### Suggesting Enhancements

Enhancement suggestions are tracked as GitHub issues. Include:

- **Use case** — what problem does this solve?
- **Proposed solution** — how should it work?
- **Alternatives considered** — what other approaches did you think about?

### Pull Requests

- Fill in the required template
- Ensure all tests pass
- Update documentation if you change behavior
- Follow the code style guidelines
- Keep PRs focused — one feature/fix per PR

---

## Development Setup

### Prerequisites

- Node.js 20 LTS
- Python 3.11+
- Redis 7.x
- PostgreSQL 14+

### Initial Setup

```bash
# Clone the repository
git clone https://github.com/Elvio11/MTU.git
cd MTU

# Install dependencies
npm install
pip install -r requirements.txt

# Set up environment
cp .env.example .env
# Edit .env with your configuration

# Build TypeScript
npm run build

# Start Redis
redis-server --daemonize yes

# Run tests to verify setup
npm test
python -m pytest tests/unit/ -v
```

### Running the System

```bash
# Development: start all agents via PM2
npm run start:all

# Or start individual agents
npm run start:ares
npm run start:sentinel
npm run start:janus

# Dashboard
cd dashboard && npm run dev
```

---

## Code Style

### Python

- Follow [PEP 8](https://peps.python.org/pep-0008/) conventions
- Use `ruff` for linting and formatting
- Type hints on all function signatures
- Docstrings for all public functions and classes (Google style)
- Maximum line length: 120 characters
- Use `async/await` consistently for async code

```python
# Good
async def check_mint_authority(mint: str) -> bool:
    """Check if mint authority has been revoked.

    Args:
        mint: The token mint address in base58.

    Returns:
        True if authority is revoked (null), False otherwise.
    """
    ...

# Bad — no type hints, no docstring
async def check_mint(mint):
    ...
```

### TypeScript

- Use ESLint with the project's configuration
- Strict mode enabled in `tsconfig.json`
- Use `const` over `let`, avoid `var`
- Explicit return types on all functions
- JSDoc comments for public APIs
- Use async/await over raw promises

```typescript
// Good
async function executeTrade(mint: string, correlationId: string): Promise<void> {
  // Implementation
}

// Bad — implicit any, no return type
async function executeTrade(mint, correlationId) {
  // Implementation
}
```

### Naming Conventions

| Element | Convention | Example |
|---------|------------|---------|
| Python variables/functions | snake_case | `check_mint_authority` |
| Python classes | PascalCase | `CircuitBreaker` |
| TypeScript variables/functions | camelCase | `executeTrade` |
| TypeScript classes | PascalCase | `AresAgent` |
| Constants | UPPER_SNAKE_CASE | `MAX_TRADES_PER_HOUR` |
| Redis keys | `mtus:` prefix | `mtus:agent:AGT-01:health` |
| Redis channels | `mtus:channel:` prefix | `mtus:channel:trade_approved` |
| Agent IDs | `AGT-XX` format | `AGT-05` |

---

## Testing

### Requirements

- All new code must include tests
- Existing tests must continue to pass
- Aim for meaningful coverage (not just line coverage)

### Running Tests

```bash
# Python unit tests
python -m pytest tests/unit/ -v

# Python integration tests (requires Redis)
python -m pytest tests/integration/ -v

# TypeScript tests
npm test

# TypeScript with coverage
npm run test:coverage

# Dashboard tests
cd dashboard && npm run test:run

# All tests
npm test && python -m pytest tests/ -v
```

### Test Categories

| Category | Purpose | Location |
|----------|---------|----------|
| Unit | Test individual functions/classes in isolation | `tests/unit/`, `*.test.ts` |
| Integration | Test real interactions (Redis, DB) | `tests/integration/` |
| E2E | Test complete trade flow end-to-end | `tests/e2e/` |
| Chaos | Test resilience under failure conditions | `tests/chaos/` |
| Security | Test encryption, auth, validation | `tests/security/` |

---

## Pull Request Process

1. **Create a branch** from `main` using the naming convention below
2. **Make your changes** following the code style guidelines
3. **Write or update tests** for your changes
4. **Run all tests** locally before pushing
5. **Update documentation** if behavior changes
6. **Open a PR** with a clear title and description
7. **Address review feedback** promptly

### PR Checklist

- [ ] Tests pass locally (`npm test && python -m pytest tests/ -v`)
- [ ] Code follows style guidelines
- [ ] Documentation updated (README, AGENT.md, etc.)
- [ ] No secrets or credentials in the diff
- [ ] PR title follows conventional commit format
- [ ] Changelog entry added (if applicable)

### PR Description Template

```markdown
## Summary
Brief description of what this PR does and why.

## Changes
- Changed X to Y because...
- Added Z to support...

## Testing
- [ ] Unit tests pass
- [ ] Integration tests pass
- [ ] Manual testing performed

## Breaking Changes
None / List any breaking changes
```

---

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

### Types

| Type | When to Use |
|------|-------------|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `style` | Code style changes (formatting, no logic change) |
| `refactor` | Code restructuring (no behavior change) |
| `test` | Adding or updating tests |
| `chore` | Maintenance tasks, dependencies |
| `perf` | Performance improvements |
| `security` | Security fixes |

### Examples

```
feat(agents): add HydraAgent for trending token detection
fix(sentinel): correct trailing stop calculation for edge case
docs(readme): update architecture diagram and agent registry
test(anansi): add unit tests for G3-G9 safety gates
chore(deps): bump @solana/web3.js from 1.98.3 to 1.98.4
security(keystore): increase Argon2id memory cost to 65536
```

---

## Branch Naming

| Type | Format | Example |
|------|--------|---------|
| Feature | `feature/<description>` | `feature/hydra-agent` |
| Bug Fix | `fix/<description>` | `fix/sentinel-trailing-stop` |
| Documentation | `docs/<description>` | `docs/update-readme` |
| Refactor | `refactor/<description>` | `refactor/redis-client` |
| Test | `test/<description>` | `test/add-chaos-tests` |
| Chore | `chore/<description>` | `chore/update-deps` |

---

## Architecture Decision Records (ADRs)

For significant architectural changes, create an ADR in `docs/adr/`:

```markdown
# ADR-XXX: <Title>

## Status
Accepted / Proposed / Deprecated

## Context
What is the issue that we're seeing that is motivating this decision?

## Decision
What is the change that we're proposing and/or doing?

## Consequences
What becomes easier or more difficult to do because of this change?
```

---

Thank you for contributing to MTUS!
