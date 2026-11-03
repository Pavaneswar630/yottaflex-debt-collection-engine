"""Deterministic checks for unsafe collection outreach language."""

import re
from dataclasses import dataclass


_THREAT_PATTERNS = (
    re.compile(
        r"\b(?:we|i)\s+(?:will|shall|are going to|might)\s+"
        r"(?:sue|arrest|prosecute|garnish|seize|report you|send the police)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:you will be arrested|go to jail|legal action will be taken|"
        r"we will take legal action)\b",
        re.IGNORECASE,
    ),
)
_THIRD_PARTY_PATTERNS = (
    re.compile(
        r"\b(?:tell|inform|notify|disclose to|contact|call)\b"
        r".{0,80}\b(?:employer|boss|coworker|family|spouse|partner|"
        r"neighbor|friend|relative)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:share|reveal|disclose)\b.{0,80}\b(?:debt|balance|account)\b"
        r".{0,80}\b(?:employer|boss|family|spouse|neighbor|friend)\b",
        re.IGNORECASE,
    ),
)
_ABUSIVE_PATTERNS = (
    re.compile(
        r"\b(?:deadbeat|lazy|pathetic|irresponsible|scum|worthless|"
        r"idiot|stupid|loser)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:insult|humiliate|shame|demean|abuse)\b", re.IGNORECASE),
)
_DISPUTE_NOTICE_PATTERN = re.compile(
    r"\b(?:dispute(?:d|s|ing)?\s+(?:(?:the|this)\s+)?(?:debt|account|"
    r"accuracy|information)|(?:debt|account)\s+(?:is\s+)?inaccurate)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GuardrailResult:
    accepted: bool
    issues: tuple[str, ...]


def inspect_unsafe_request(text: str) -> tuple[str, ...]:
    """Reject explicit requests to threaten, expose, or abuse a customer."""
    issues: list[str] = []
    if any(pattern.search(text) for pattern in _THREAT_PATTERNS):
        issues.append("THREATENING_LANGUAGE")
    if any(pattern.search(text) for pattern in _THIRD_PARTY_PATTERNS):
        issues.append("THIRD_PARTY_DISCLOSURE")
    if any(pattern.search(text) for pattern in _ABUSIVE_PATTERNS):
        issues.append("ABUSIVE_LANGUAGE")
    return tuple(issues)


def validate_outreach_draft(text: str) -> GuardrailResult:
    """Reject outreach containing threats, disclosure, abuse, or no dispute notice."""
    issues = list(inspect_unsafe_request(text))
    if not _DISPUTE_NOTICE_PATTERN.search(text):
        issues.append("MISSING_DISPUTE_NOTICE")
    return GuardrailResult(accepted=not issues, issues=tuple(issues))
