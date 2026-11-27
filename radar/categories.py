"""Which kind of role a posting is, from its title, for the page's role buttons.

Checked in order, so a title that fits two groups lands in the first: "AI Product Manager" is PM,
"Forward Deployed AI
Engineer" is FDE, "Security Engineer,
Cloud Platform" is Security, "ML Platform Engineer" is AI/ML, "Data Platform" is Data.
Anything that fits none is SWE.
"""
from __future__ import annotations

import re

CATEGORIES: list[tuple[str, list[str]]] = [
    ("PM", [
        "product manager", "product management", "associate product manager", "apm",
        "technical product manager", "program manager", "program management", "technical program manager",
        "tpm", "product owner",
    ]),
    ("Security", [
        "security", "appsec", "cybersecurity", "cyber security", "devsecops", "offensive", "pentest",
        "penetration", "threat", "detection engineer",
    ]),
    ("FDE", [
        "forward deployed", "forward-deployed", "forward deploy", "fde", "deployed engineer",
        "deployment engineer", "implementation engineer", "integration engineer", "integrations engineer",
        "customer success engineer", "professional services engineer",
    ]),
    ("Solutions", [
        "solutions architect", "solution architect", "solutions engineer", "solution engineer",
        "customer engineer", "delivery consultant",
        "cloud consultant", "cloud architect", "technical consultant", "field engineer",
    ]),
    ("AI/ML", [
        "machine learning", "ml", "ai", "applied ai", "mlops", "llm", "agentic", "deep learning",
        "computer vision", "nlp", "artificial intelligence", "ai/ml", "genai", "generative",
    ]),
    ("Data", [
        "data engineer", "data engineering", "data platform", "data platforms", "analytics engineer", "data infrastructure",
        "etl", "data pipeline", "data pipelines",
    ]),
    ("DevOps/SRE", [
        "site reliability", "sre", "devops", "platform", "infrastructure", "cloud engineer",
        "cloud engineering", "production engineer", "production engineering", "reliability",
        "build engineer", "release engineer", "build and release", "systems development engineer",
        "system development engineer", "tooling", "developer productivity", "developer tools", "aiops",
    ]),
]

# The order of the buttons on the page.
ORDER = ["SWE", "FDE", "DevOps/SRE", "AI/ML", "PM", "Solutions", "Security", "Data"]


def _regex(words: list[str]) -> re.Pattern:
    parts = []
    for w in sorted(words, key=len, reverse=True):
        esc = re.escape(w.lower()).replace(r"\ ", r"[\s\-]+")
        parts.append(rf"(?<![a-z0-9]){esc}(?![a-z0-9])")
    return re.compile("|".join(parts), re.I)


_COMPILED = [(name, _regex(words)) for name, words in CATEGORIES]


def role_category(title: str) -> str:
    t = title or ""
    for name, rx in _COMPILED:
        if rx.search(t):
            return name
    return "SWE"
