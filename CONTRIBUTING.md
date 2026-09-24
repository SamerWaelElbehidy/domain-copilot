# Contributing

- Branch from `main`; never push directly to `main`. All work merges via Pull Request.
- Conventional Commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`); messages explain why.
- Atomic commits; no commented-out code; no secrets (see `.env.example`).
- Architecture rules: `domain/` and `application/` must not import any LLM SDK, vector-store SDK, or web framework (ADR-0001).
- Run `ruff check src tests scripts` and `python -m pytest tests` before opening a PR.
