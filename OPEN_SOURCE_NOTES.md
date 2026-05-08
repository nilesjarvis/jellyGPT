# Open-source release notes

This repository has been prepared for public review with the following assumptions:

- Source code, tests, documentation, and synthetic benchmark fixtures are safe to publish.
- Real Jellyfin API keys, databases, personal watch history, generated recommendation caches, and local deployment files must remain uncommitted.
- Ollama-related features are experimental and disabled by default.
- The current active integration is `POST /recommendations` with caller-provided candidate metadata; the cached `GET /recommendations` path is intentionally still a placeholder.

## Sanitization performed

- Removed private-person references and local machine paths from public docs.
- Replaced personal container image namespaces with `YOUR_GITHUB_USER_OR_ORG` placeholders.
- Added `.dockerignore` and `.gitignore` rules for local secrets, generated compose files, caches, databases, logs, profiles, and build output.
- Added `LICENSE` and `SECURITY.md`.
- Updated API and architecture docs to match current behavior.
- Regenerated benchmark JSON with synthetic data only.

## Pre-publish checklist

Before pushing to a public repository:

1. Run tests and lint:
   ```bash
   pytest -q
   ruff check src tests bench_ai_features.py install.py
   ```
2. Confirm there are no private markers:
   ```bash
   git status --short
   git diff --stat
   ```
3. Review every staged file:
   ```bash
   git diff --cached
   ```
4. Confirm `.env`, databases, caches, and local compose files are not staged.
5. Replace `YOUR_GITHUB_USER_OR_ORG` with your public registry namespace only if you intend to publish container images.
