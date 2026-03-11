[Back to README](./README.md)

# Contributing

Thank you for your interest in contributing to OpenForexAI.

## Scope

Contributions are welcome for:
- Bug fixes
- Documentation improvements
- Tests and reliability improvements
- New adapters, tools, and non-breaking enhancements

## Ground Rules

- Keep changes focused and reviewable.
- Follow existing project architecture and coding conventions.
- Avoid unrelated refactors in the same change.
- Do not commit secrets or credentials.

## Development Setup

See [`setup.md`](./setup.md) for installation and startup instructions.

## Code Quality

Before submitting, run:

```bash
ruff check .
mypy openforexai
pytest
```

If your change touches only a specific area, run the most relevant subset in addition to full checks when possible.

## Commit and PR Guidelines

- Use clear commit messages in imperative form.
- Include a concise PR description:
  - What changed
  - Why it changed
  - How it was tested
- Reference related issues or tasks.
- Add screenshots for UI changes.

## Testing Expectations

- Add or update tests for behavior changes.
- Prefer unit tests for logic and integration tests for cross-component behavior.
- Avoid reducing existing test coverage.

## Documentation Expectations

- Update docs when changing behavior, configuration, or APIs.
- Keep `README.md` and topic files (`architecture.md`, `setup.md`, `developer.md`) consistent.

## Security and Secrets

- Never commit API keys, account IDs, or private credentials.
- Use environment variables and local `.env` files.

## Review Process

Maintainers may request revisions before merge. Please keep discussions technical and focused on behavior, risk, and maintainability.

---

This file is a baseline template and can be extended with repository-specific workflow details (branching model, release process, code owners, etc.).
