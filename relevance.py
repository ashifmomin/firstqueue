"""Deterministic, explainable relevance engine for LinkedIn-only job alerts.

NOC Engineer and Cloud Support Engineer are intentionally not target roles.
The engine normalizes spelling/spacing variants such as Help Desk/Helpdesk and
uses role-family evidence before technical/support context.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Set, Tuple

import config

_WORD_RE = re.compile(r"[a-z0-9+#.]+", re.I)


def normalize_text(text: str) -> str:
    text = (text or "").lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[\u2010-\u2015\-/]+", " ", text)
    text = re.sub(r"\bhelp\s*desk\b", "helpdesk", text)
    text = re.sub(r"\bservice\s*desk\b", "service desk", text)
    text = re.sub(r"\bit\s+support\b", "it support", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokens(text: str) -> Set[str]:
    return set(x.lower() for x in _WORD_RE.findall(normalize_text(text)))


def _contains_phrase(text: str, phrase: str) -> bool:
    return normalize_text(phrase) in normalize_text(text)


def _fuzzy_phrase_score(title: str, phrase: str) -> float:
    a = normalize_text(title)
    b = normalize_text(phrase)
    if not a or not b:
        return 0.0
    raw = SequenceMatcher(None, a, b).ratio()
    at = " ".join(sorted(_tokens(a)))
    bt = " ".join(sorted(_tokens(b)))
    token = SequenceMatcher(None, at, bt).ratio()
    return max(raw, token)


def _count_hits(text: str, terms: List[str]) -> Tuple[int, List[str]]:
    low = normalize_text(text)
    hits = [term for term in terms if normalize_text(term) in low]
    return len(hits), hits


def _optional_embedding_score(query: str, document: str) -> Optional[float]:
    if not config.ENABLE_EMBEDDING_MODEL:
        return None
    try:
        from sentence_transformers import SentenceTransformer
    except Exception:
        return None
    try:
        model = _optional_embedding_score.model  # type: ignore[attr-defined]
    except AttributeError:
        try:
            model = SentenceTransformer(config.EMBEDDING_MODEL_NAME)
            _optional_embedding_score.model = model  # type: ignore[attr-defined]
        except Exception:
            return None
    try:
        vectors = model.encode([query, document], normalize_embeddings=True)
        similarity = float(sum(a * b for a, b in zip(vectors[0], vectors[1])))
        return max(0.0, min(100.0, (similarity + 1.0) * 50.0))
    except Exception:
        return None


def score_job(title: str, description: str, query: Optional[str] = None) -> Dict[str, Any]:
    title = title or ""
    description = description or ""
    full = title + "\n" + description
    query = query or config.RELEVANCE_QUERY

    score = 0.0
    reasons: List[str] = []
    negative_reasons: List[str] = []
    matched_families: List[str] = []

    normalized_title = normalize_text(title)

    # Exact role-family title match is the strongest signal.
    for family, phrases in config.ROLE_FAMILIES.items():
        if any(_contains_phrase(title, phrase) for phrase in phrases):
            matched_families.append(family)

    if matched_families:
        score += 45.0
        reasons.append("target support role in title")
        if len(matched_families) > 1:
            score += 4.0

    # Generic support-title variants, but avoid treating every Support Manager as target.
    generic_title_hits, generic_title_terms = _count_hits(
        title, ["support analyst", "support specialist", "support engineer", "support representative", "support agent"]
    )
    if generic_title_hits and not matched_families:
        score += 32.0
        reasons.append("support role in title")

    # Exact role phrase bonus.
    exact_title = [k for k in config.ROLE_KEYWORDS if _contains_phrase(title, k)]
    exact_desc = [k for k in config.ROLE_KEYWORDS if _contains_phrase(description, k)]
    if exact_title:
        score += 25.0
        reasons.append("exact target role phrase in title")
    elif exact_desc:
        score += 7.0
        reasons.append("target role phrase in description")

    # Technical and support context.
    tech_hits, tech_terms = _count_hits(full, config.TECHNICAL_SIGNALS)
    support_hits, support_terms = _count_hits(full, config.SUPPORT_SIGNALS)
    score += min(17.0, tech_hits * 2.5)
    score += min(12.0, support_hits * 2.0)
    if tech_hits:
        reasons.append("technical-support signals")
    if support_hits:
        reasons.append("support/customer-service signals")

    # Description-only support should remain materially weaker than title evidence.
    desc_role_hits, desc_roles = _count_hits(description, config.DESCRIPTION_ROLE_PATTERNS)
    if desc_role_hits and not matched_families and not generic_title_hits:
        score += min(15.0, 7.0 + 3.0 * min(desc_role_hits - 1, 2))
        reasons.append("support-role language in description")

    # Fuzzy title similarity helps variants such as "Application Support (L2)".
    best_phrase = ""
    best_fuzzy = 0.0
    for phrase in config.ROLE_KEYWORDS + ["support analyst", "support specialist", "support engineer"]:
        sim = _fuzzy_phrase_score(title, phrase)
        if sim > best_fuzzy:
            best_fuzzy = sim
            best_phrase = phrase
    if best_fuzzy >= 0.78 and not matched_families:
        score += 10.0
        reasons.append("title is close to target role")
    elif best_fuzzy >= 0.64 and not matched_families:
        score += 5.0
        reasons.append("title is partially similar to target role")

    # Negative commercial role signals.
    neg_title_hits, neg_title_terms = _count_hits(title, config.NEGATIVE_TITLE_TERMS)
    neg_desc_hits, neg_desc_terms = _count_hits(description, config.NEGATIVE_DESCRIPTION_TERMS)
    if neg_title_hits:
        score -= min(80.0, 42.0 * neg_title_hits)
        negative_reasons.extend("non-target title: " + x for x in neg_title_terms[:3])
    if neg_desc_hits:
        score -= min(28.0, 7.0 * neg_desc_hits)
        negative_reasons.extend("non-target description: " + x for x in neg_desc_terms[:4])

    # Soft commercial terms are only penalized when no strong technical-support title exists.
    soft_commercial = ["account manager", "customer success", "client relationship", "sales"]
    soft_hits, soft_terms = _count_hits(title, soft_commercial)
    if soft_hits and not matched_families:
        score -= min(35.0, 18.0 * soft_hits)
        negative_reasons.extend("commercial title signal: " + x for x in soft_terms[:3])

    embedding_score = _optional_embedding_score(query, full[: config.EMBEDDING_TEXT_MAX_CHARS])
    if embedding_score is not None:
        score = (score * 0.80) + (embedding_score * 0.20)
        if embedding_score >= config.EMBEDDING_STRONG_THRESHOLD:
            reasons.append("embedding similarity")

    score = max(0.0, min(100.0, round(score, 1)))
    if score >= config.RELEVANCE_HIGH_THRESHOLD:
        band = "HIGH"
    elif score >= config.RELEVANCE_ALERT_THRESHOLD:
        band = "MEDIUM"
    else:
        band = "LOW"

    reasons = list(dict.fromkeys(reasons))
    negative_reasons = list(dict.fromkeys(negative_reasons))
    return {
        "score": score,
        "band": band,
        "matched_role": exact_title[0] if exact_title else (matched_families[0] if matched_families else best_phrase),
        "matched_families": matched_families,
        "reasons": reasons[:6],
        "negative_reasons": negative_reasons[:6],
        "embedding_score": round(embedding_score, 1) if embedding_score is not None else None,
        "title_role_hits": generic_title_terms + exact_title,
        "description_role_hits": desc_roles[:8],
        "technical_hits": tech_terms[:8],
        "support_hits": support_terms[:8],
    }


def should_alert(result: Dict[str, Any]) -> bool:
    if result["score"] < config.RELEVANCE_ALERT_THRESHOLD:
        return False
    if result["negative_reasons"] and result["score"] < config.RELEVANCE_OVERRIDE_NEGATIVE_THRESHOLD:
        return False
    return True
