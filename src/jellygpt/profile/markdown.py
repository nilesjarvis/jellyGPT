from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

PROFILE_VERSION = "1"
REQUIRED_HEADINGS = [
    "## Stable Preferences",
    "## Emerging Interests",
    "## Negative Signals / Avoid",
    "## Watch Patterns",
    "## Recommendation Guidance",
    "## Update Log",
]

LAST_EVENT_RE = re.compile(r"<!-- jellygpt-last-event-id: (.*?) -->")
LAST_PLAYED_RE = re.compile(r"<!-- jellygpt-last-played-at: (.*?) -->")


def initial_profile(user_id: str | None = None) -> str:
    now = datetime.now(timezone.utc).isoformat()
    subject = f" for user `{user_id}`" if user_id else ""
    return f"""# jellyGPT Taste Profile{subject}

<!-- jellygpt-profile-version: {PROFILE_VERSION} -->
<!-- jellygpt-last-event-id:  -->
<!-- jellygpt-last-played-at:  -->
<!-- jellygpt-updated-at: {now} -->

## Stable Preferences

- Not enough watch-history evidence yet.

## Emerging Interests

- Not enough recent evidence yet.

## Negative Signals / Avoid

- Not enough skip/abandonment evidence yet.

## Watch Patterns

- Not enough watch-time evidence yet.

## Recommendation Guidance

- Start with deterministic `blended` recommendations until enough taste evidence accumulates.

## Update Log
"""


def read_profile(path: Path, user_id: str | None = None) -> str:
    if path.exists():
        return path.read_text(encoding="utf-8")
    return initial_profile(user_id=user_id)


def extract_last_event_id(markdown: str) -> str | None:
    match = LAST_EVENT_RE.search(markdown)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def extract_last_played_at(markdown: str) -> str | None:
    match = LAST_PLAYED_RE.search(markdown)
    if not match:
        return None
    value = match.group(1).strip()
    return value or None


def update_markers(markdown: str, last_event_id: str, last_played_at: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    replacements = {
        r"<!-- jellygpt-last-event-id: .*? -->": f"<!-- jellygpt-last-event-id: {last_event_id} -->",
        r"<!-- jellygpt-last-played-at: .*? -->": f"<!-- jellygpt-last-played-at: {last_played_at} -->",
        r"<!-- jellygpt-updated-at: .*? -->": f"<!-- jellygpt-updated-at: {now} -->",
    }
    out = markdown
    for pattern, replacement in replacements.items():
        if re.search(pattern, out):
            out = re.sub(pattern, replacement, out, count=1)
        else:
            out = replacement + "\n" + out
    return out


def append_update(markdown: str, update_markdown: str, last_event_id: str, last_played_at: str) -> str:
    if "## Update Log" not in markdown:
        markdown = markdown.rstrip() + "\n\n## Update Log\n"
    timestamp = datetime.now(timezone.utc).isoformat()
    section = f"\n### {timestamp}\n\n{update_markdown.strip()}\n"
    markdown = markdown.rstrip() + "\n" + section
    return update_markers(markdown, last_event_id=last_event_id, last_played_at=last_played_at)


def write_profile_atomic(path: Path, markdown: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(path)


def looks_like_valid_update(markdown: str) -> bool:
    text = markdown.strip()
    if len(text) < 80:
        return False
    return any(marker in text for marker in ["Preference", "Signal", "Pattern", "Guidance", "Evidence", "Watch"])
