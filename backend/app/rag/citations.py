"""Citation assembler.

Spans are parsed out of corpus/sources/*.md at import and are never rewritten,
so every claim the API makes can be traced to an exact line of an exact file at
an exact sha256. Nothing is generated, and no model is called.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from functools import lru_cache
from pathlib import Path

from backend.app.models.schemas import Citation
from model.anomaly import (
    PRESSURE_VARIANCE_ALERT, TEMP_RISE_THRESHOLD, VIB_ALERT, VIB_NORMAL,
)

CORPUS_DIR = Path(__file__).resolve().parents[3] / "corpus"
SOURCES_DIR = CORPUS_DIR / "sources"
MANIFEST_PATH = CORPUS_DIR / "manifest.json"
FALLBACK_VERSION = "bloompulse-unversioned"

MAX_CITATIONS = 4

logger = logging.getLogger("bloompulse")


@lru_cache(maxsize=1)
def corpus_version() -> str:
    try:
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))["version"]
    except (OSError, json.JSONDecodeError, KeyError):
        logger.warning("corpus manifest unreadable at %s, using fallback", MANIFEST_PATH)
        return FALLBACK_VERSION


def file_digest(path: Path) -> str:
    """sha256 of a corpus file, used as the version hash on every span."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_type(heading: str, filename: str) -> str:
    lowered = heading.lower()
    if "directive" in lowered or lowered.startswith("osha directive"):
        return "directive"
    if lowered.startswith("sec 1910"):
        return "statute"
    if "iso " in lowered or lowered.startswith("iso"):
        return "standard"
    return "manual" if "manual" in filename else "standard"


def _parse_document(path: Path) -> dict[str, Citation]:
    """Pull every `## heading` section with a blockquote into one Citation.

    The expected shape, which the corpus files already use:

        ## Some heading
        > "the verbatim span"
        **Locator:** where in the document
        **Source:** https://example.org
    """
    digest = file_digest(path)
    text = path.read_text(encoding="utf-8")
    found: dict[str, Citation] = {}

    # Split on level-2 headings, keeping the heading with its body.
    sections = re.split(r"^##\s+", text, flags=re.MULTILINE)[1:]
    for section in sections:
        lines = section.splitlines()
        heading = lines[0].strip()

        quote_lines = [
            line.lstrip("> ").strip()
            for line in lines[1:]
            if line.lstrip().startswith(">")
        ]
        if not quote_lines:
            continue
        span = " ".join(quote_lines).strip().strip('"').strip()

        locator_match = re.search(r"^\*\*Locator:\*\*\s*(.+)$", section, re.MULTILINE)
        source_match = re.search(r"(https?://\S+)", section)

        # A source line that flags itself as written for the demo is carried
        # through to the response rather than quietly dropped.
        synthetic = "synthetic" in section.lower()

        slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")[:48]
        found[heading] = Citation(
            id=f"cite-{slug}",
            source_type=_source_type(heading, path.name),  # type: ignore[arg-type]
            title=heading,
            span_text=span,
            deep_link=source_match.group(1).rstrip(".,") if source_match else "",
            locator=locator_match.group(1).strip() if locator_match else heading,
            version_hash=f"sha256:{digest[:16]}",
            synthetic=synthetic,
        )
    return found


@lru_cache(maxsize=1)
def passages() -> dict[str, Citation]:
    """Every parsed span, keyed by its heading. Read once per process."""
    collected: dict[str, Citation] = {}
    for path in sorted(SOURCES_DIR.glob("*.md")):
        collected.update(_parse_document(path))
    if not collected:
        logger.error("no corpus passages parsed from %s", SOURCES_DIR)
    return collected


# Heading in the corpus that backs each kind of claim. A missing heading is a
# corpus error, and the test suite fails on it rather than the API going quiet.
BACKING = {
    "vibration": "ISO 10816-3 - Vibration Severity (Industrial)",
    "temperature": "Bearing Unit Model: NTN UCFCX05",
    "pressure": "Siemens Simotics Motor - Predictive Thresholds",
    "lockout": "Sec 1910.147 - Control of Hazardous Energy (Lockout/Tagout)",
    "guarding": "Sec 1910.212 - General Requirements for All Machines",
    "thresholds": "OSHA Directive CPL 02-00-147 - Vibration Thresholds (Predictive Maintenance)",
}


def _cite(key: str, applies_to: str) -> Citation | None:
    passage = passages().get(BACKING[key])
    if passage is None:
        logger.error("corpus is missing the passage backing %r", key)
        return None
    return passage.model_copy(update={"applies_to": applies_to})


def citations_for(anomaly: dict) -> list[Citation]:
    """Attach the passages that actually govern this verdict."""
    severity = anomaly.get("severity", "normal")
    metrics = anomaly.get("metrics") or {}
    vib = metrics.get("max_vib", 0.0)
    temp_rise = metrics.get("max_temp_rise", 0.0)
    pressure_var = metrics.get("pressure_var", 0.0)

    out: list[Citation | None] = []

    if vib > VIB_ALERT:
        out.append(_cite("vibration", f"Vibration {vib} mm/s is above the {VIB_ALERT} mm/s Zone C/D boundary."))
    elif vib > VIB_NORMAL:
        out.append(_cite("vibration", f"Vibration {vib} mm/s is above the {VIB_NORMAL} mm/s Zone B/C boundary."))
    else:
        out.append(_cite("vibration", f"Vibration {vib} mm/s sits inside Zone A/B, where operation is unrestricted."))

    if temp_rise > TEMP_RISE_THRESHOLD:
        out.append(_cite("temperature", f"Temperature is {temp_rise} C above baseline, past the {TEMP_RISE_THRESHOLD} C inspection trigger."))
    if pressure_var > PRESSURE_VARIANCE_ALERT:
        out.append(_cite("pressure", f"Pressure variance {pressure_var}% is past the {PRESSURE_VARIANCE_ALERT}% seal-replacement threshold."))

    if severity in ("alert", "critical"):
        out.append(_cite("lockout", "Servicing this machine requires energy isolation before work begins."))
        out.append(_cite("guarding", "Rotating parts are the hazard class driving this verdict."))

    seen: set[str] = set()
    unique: list[Citation] = []
    for citation in out:
        if citation is not None and citation.id not in seen:
            unique.append(citation)
            seen.add(citation.id)
    return unique[:MAX_CITATIONS]
