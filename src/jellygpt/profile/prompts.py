CHUNK_SUMMARY_PROMPT = """You are analyzing Jellyfin watch-history data for a self-hosted recommendation service.

Task:
Summarize this watch-history chunk into Markdown notes for a long-term taste profile.

Rules:
- Do not invent facts, titles, genres, or user preferences.
- Prefer repeated behavior over one-off watches.
- Treat high completion and rewatches as positive signals.
- Treat very low completion, quick abandonment, or repeated skips as negative signals.
- Separate stable signals from weak/emerging signals.
- Mention uncertainty when evidence is thin.
- Keep output concise.
- Output Markdown only. No JSON.

Return sections:
## Strong Positive Signals
## Weak or Emerging Signals
## Negative / Skip Signals
## Genre, Mood, and Format Patterns
## Watch-Time Patterns
## Notable Evidence
## Open Questions / Uncertainty

Existing profile excerpt:
{existing_profile}

Watch-history chunk:
{chunk_text}
"""

PROFILE_UPDATE_PROMPT = """You maintain a long-term Jellyfin taste profile in Markdown.

Task:
Create one concise Markdown update section using the new chunk summaries.

Important:
- Continue improving the existing profile; do not replace it blindly.
- Preserve useful prior conclusions unless contradicted by newer evidence.
- Add new evidence where meaningful.
- Downgrade claims that look weak, stale, or contradicted.
- Keep it useful for recommendations.
- Do not invent preferences.
- Output only the update section Markdown, not the full profile.
- No JSON.

Existing profile:
{existing_profile}

New evidence summaries:
{chunk_summaries}

Return sections:
## Stable Preferences
## Emerging Interests
## Negative Signals / Avoid
## Watch Patterns
## Recommendation Guidance
## Evidence Notes
"""
