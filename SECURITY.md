# Security Policy

## Supported versions

jellyGPT is pre-1.0 software. Security fixes are expected to land on the default branch until a release policy exists.

## Reporting a vulnerability

Please do not open public issues for vulnerabilities that expose credentials, Jellyfin databases, or private watch history.

If this project is published on GitHub, use the repository's private vulnerability reporting feature if available. Otherwise, contact the maintainer privately through the published repository profile.

## Data and credential handling

jellyGPT is designed for self-hosted media environments and can be configured with private Jellyfin paths and API keys.

Do not commit:

- `.env` or generated `docker-compose.local.yml`
- Jellyfin API keys
- Jellyfin or Playback Reporting databases
- cached recommendation outputs from a real personal library
- generated taste-profile Markdown from real watch history
- logs containing local paths, service URLs, tokens, or media titles you consider private

The example files in this repository use placeholder values only.
