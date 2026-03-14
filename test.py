"""
Clinical AI Pipeline Evaluation Framework
==========================================
Entry point: python test.py <input.json> <output.json>

Evaluates extracted clinical entities across six dimensions:
  1. Entity Type Error Rate
  2. Assertion Error Rate
  3. Temporality Error Rate
  4. Subject Error Rate
  5. Event Date Accuracy
  6. Attribute Completeness
"""

import json
import sys
import os
import re
from collections import defaultdict
from typing import Any

# ---------------------------------------------------------------------------
# CONSTANTS & VALIDATION RULES
# ---------------------------------------------------------------------------

VALID_ENTITY_TYPES = {
    "MEDICINE", "PROBLEM", "PROCEDURE", "TEST", "VITAL_NAME",
    "IMMUNIZATION", "MEDICAL_DEVICE", "MENTAL_STATUS", "SDOH", "SOCIAL_HISTORY"
}

VALID_ASSERTIONS    = {"POSITIVE", "NEGATIVE", "UNCERTAIN"}
VALID_TEMPORALITIES = {"CURRENT", "CLINICAL_HISTORY", "UPCOMING", "UNCERTAIN"}
VALID_SUBJECTS      = {"PATIENT", "FAMILY_MEMBER"}

# ---------------------------------------------------------------------------
# TYPE-CONTEXT RULES
# Entity keywords that are VERY unlikely to belong to certain types.
# Format: { entity_type : [ (regex_pattern, wrong_if_matches), ... ] }
# ---------------------------------------------------------------------------

# Keywords that signal an entity is NOISE / admin boilerplate
ADMIN_NOISE_PATTERNS = [
    r"\bencounter \d+\b",
    r"\bhospital account\b",
    r"\bguarantor account\b",
    r"\bf/o payor\b",
    r"\bhmo subscriber\b",
    r"\brcvd\b",
    r"^pt$",
    r"\bnotes from \[encounter",
    r"\bplan of care by \[provider",
    r"\bcm/sw plan of care notes\b",
    r"\bcm/sw discharge plan progress\b",
    r"\bdischarge summary notes\b",
    r"\bdischarge summary by \[provider",
    r"\brecord reviewed\b",
    r"\bmedications reviewed\b",
    r"\bmedications reviewed at this visit\b",
    r"\bactive medications\b",
    r"\bdischarge medications\b",
    r"\bdiscontinued medications\b",
    r"\bpharmacy chart note\b",
    r"\bop referrals\b",
    r"\bdme orders\b",
    r"\battention payor\b",
    r"\breadmission information\b",
]

# Type mismatch rules: (entity_type_assigned, keyword_pattern) → likely error
TYPE_MISMATCH_RULES = [
    # Medical conditions / diagnoses tagged as wrong types
    ("MEDICAL_DEVICE",  r"\bcellulitis\b"),
    ("MEDICAL_DEVICE",  r"\bwound\b"),
    ("SDOH",            r"\bstreptococcus\b"),
    ("SDOH",            r"\bmrsa\b"),
    ("SDOH",            r"\boxycodone\b"),
    ("SDOH",            r"\brefusing\b"),
    ("MEDICINE",        r"\bambulation\b"),
    ("MEDICINE",        r"\badl trial\b"),
    ("MEDICINE",        r"\barterial us\b"),
    ("SOCIAL_HISTORY",  r"\bwound care\b"),
    ("VITAL_NAME",      r"\bincision care\b"),
    ("VITAL_NAME",      r"\bcm/sw\b"),
    ("VITAL_NAME",      r"\brecord review\b"),
    ("IMMUNIZATION",    r"\bskilled nursing\b"),
    ("PROBLEM",         r"\baka\b"),
    ("PROCEDURE",       r"\bindependent filed\b"),
    ("MENTAL_STATUS",   r"\battention payor\b"),
    ("MENTAL_STATUS",   r"\bdischarge summary by\b"),
    # Legal boilerplate extracted as clinical entities
    ("PROBLEM",         r"alcohol and drug abuse.*federal"),
    ("PROBLEM",         r"drug and alcohol abuse.*federal"),
]

# Temporality mismatch: (assigned_temporality, keyword_pattern) → likely error
TEMPORALITY_MISMATCH_RULES = [
    # Past events tagged as UPCOMING
    ("UPCOMING", r"\bno previous admission\b"),
    ("UPCOMING", r"\breadmission within the last 30 days\b"),
    ("UPCOMING", r"\ber admits\b"),
    ("UPCOMING", r"\bdrug and alcohol abuse\b"),   # legal boilerplate
    ("UPCOMING", r"\badmission list\b"),
    # Active clinical problems tagged as UNCERTAIN
    ("UNCERTAIN", r"\bleft ankle cellulitis\b"),
    # Current procedures tagged as UPCOMING
    ("UPCOMING",  r"\bcm/sw plan of care notes\b"),
]

# Assertion must not be empty for clinical entities
CLINICAL_TYPES_REQUIRING_ASSERTION = {
    "MEDICINE", "PROBLEM", "TEST", "VITAL_NAME", "MENTAL_STATUS"
}

# Metadata relations expected for MEDICINE entities
MEDICINE_EXPECTED_RELATIONS = {"ROUTE", "FREQUENCY", "DOSE", "STRENGTH", "UNIT", "FORM", "DURATION", "STATUS"}

# Spurious medication metadata on non-medication entities (hallucination signal)
MEDICATION_META_TYPES = {"STRENGTH", "UNIT", "DOSE", "FORM", "FREQUENCY", "ROUTE", "DURATION"}
NON_MEDICATION_TYPES  = {"PROCEDURE", "VITAL_NAME", "SDOH", "SOCIAL_HISTORY", "MENTAL_STATUS", "TEST"}

# ---------------------------------------------------------------------------
# HELPERS
# ---------------------------------------------------------------------------

def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(data: Any, path: str):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

def normalise(text: str) -> str:
    return (text or "").lower().strip()

def matches_any(text: str, patterns: list) -> bool:
    t = normalise(text)
    return any(re.search(p, t) for p in patterns)

def is_admin_noise(entity_text: str) -> bool:
    return matches_any(entity_text, ADMIN_NOISE_PATTERNS)

def has_type_mismatch(entity_type: str, entity_text: str) -> bool:
    for wrong_type, pattern in TYPE_MISMATCH_RULES:
        if entity_type == wrong_type and re.search(pattern, normalise(entity_text)):
            return True
    return False

def has_temporality_mismatch(temporality: str, entity_text: str) -> bool:
    for wrong_temp, pattern in TEMPORALITY_MISMATCH_RULES:
        if temporality == wrong_temp and re.search(pattern, normalise(entity_text)):
            return True
    return False

def has_spurious_medication_metadata(entity_type: str, relations: list) -> bool:
    """Flag non-medication entities that have medication-style metadata attached."""
    if entity_type not in NON_MEDICATION_TYPES:
        return False
    for rel in relations:
        if rel.get("entity_type") in MEDICATION_META_TYPES:
            return True
    return False

def missing_assertion(entity_type: str, assertion: str) -> bool:
    if entity_type in CLINICAL_TYPES_REQUIRING_ASSERTION:
        return assertion not in VALID_ASSERTIONS
    return False

def medicine_attribute_completeness(relations: list) -> float:
    """What fraction of expected medicine metadata slots are filled?"""
    found = {r.get("entity_type") for r in relations}
    core  = {"ROUTE", "DOSE", "FREQUENCY"}          # minimum expected
    score = len(core & found) / len(core)
    return round(score, 4)

# ---------------------------------------------------------------------------
# CORE EVALUATOR
# ---------------------------------------------------------------------------

def evaluate(records: list) -> dict:
    """
    Evaluates a list of entity records and returns the output schema.
    Error rate = proportion of entities of that category that contain an error.
    """

    # Per-type counters: {type: [total, errors]}
    type_counts   = defaultdict(lambda: [0, 0])
    assert_counts = defaultdict(lambda: [0, 0])
    temp_counts   = defaultdict(lambda: [0, 0])
    subj_counts   = defaultdict(lambda: [0, 0])

    date_scores        = []
    completeness_scores = []
    noise_count        = 0

    for rec in records:
        entity       = rec.get("entity", "")
        entity_type  = (rec.get("entity_type") or "").upper()
        assertion    = (rec.get("assertion")   or "").upper()
        temporality  = (rec.get("temporality") or "").upper()
        subject      = (rec.get("subject")     or "").upper()
        meta         = rec.get("metadata_from_qa", {}) or {}
        relations    = meta.get("relations", []) or []
        text         = rec.get("text", "")
        heading      = rec.get("heading", "")

        # ── noise detection ──────────────────────────────────────────────
        if is_admin_noise(entity):
            noise_count += 1
            # Count as errors in all dimensions for the assigned type
            if entity_type in VALID_ENTITY_TYPES:
                type_counts[entity_type][0] += 1
                type_counts[entity_type][1] += 1
            if assertion in VALID_ASSERTIONS:
                assert_counts[assertion][0] += 1
                assert_counts[assertion][1] += 1
            if temporality in VALID_TEMPORALITIES:
                temp_counts[temporality][0] += 1
                temp_counts[temporality][1] += 1
            if subject in VALID_SUBJECTS:
                subj_counts[subject][0] += 1
                subj_counts[subject][1] += 1
            continue

        # ── entity type evaluation ────────────────────────────────────────
        if entity_type in VALID_ENTITY_TYPES:
            type_counts[entity_type][0] += 1
            error = False

            # 1. Type mismatch rules
            if has_type_mismatch(entity_type, entity):
                error = True

            # 2. Spurious medication metadata
            if has_spurious_medication_metadata(entity_type, relations):
                error = True

            if error:
                type_counts[entity_type][1] += 1

        # ── assertion evaluation ──────────────────────────────────────────
        if assertion in VALID_ASSERTIONS:
            assert_counts[assertion][0] += 1
            if missing_assertion(entity_type, assertion):
                assert_counts[assertion][1] += 1
        elif entity_type in CLINICAL_TYPES_REQUIRING_ASSERTION:
            # Empty assertion on a clinical type — count as POSITIVE slot error
            assert_counts["POSITIVE"][0] += 1
            assert_counts["POSITIVE"][1] += 1

        # ── temporality evaluation ────────────────────────────────────────
        if temporality in VALID_TEMPORALITIES:
            temp_counts[temporality][0] += 1
            if has_temporality_mismatch(temporality, entity) or has_temporality_mismatch(temporality, text):
                temp_counts[temporality][1] += 1
        elif entity_type in CLINICAL_TYPES_REQUIRING_ASSERTION:
            # Empty temporality on clinical entity
            temp_counts["CURRENT"][0] += 1
            temp_counts["CURRENT"][1] += 1

        # ── subject evaluation ────────────────────────────────────────────
        if subject in VALID_SUBJECTS:
            subj_counts[subject][0] += 1
            # Flag: family-history section but tagged as PATIENT (or vice versa)
            heading_lower = normalise(heading)
            if subject == "PATIENT" and "family" in heading_lower and "history" in heading_lower:
                subj_counts["PATIENT"][1] += 1
            elif subject == "FAMILY_MEMBER" and "family" not in heading_lower:
                subj_counts["FAMILY_MEMBER"][1] += 1

        # ── event date accuracy ───────────────────────────────────────────
        # Derived dates in metadata: score 1.0 if plausible year (2015-2030),
        # 0.0 if clearly wrong (e.g. "2017-05-01" for a 2024 chart)
        for rel in relations:
            if rel.get("entity_type") == "derived_date":
                date_val = rel.get("entity", "")
                year_match = re.search(r"\b(20\d{2})\b", str(date_val))
                if year_match:
                    year = int(year_match.group(1))
                    score = 1.0 if 2020 <= year <= 2026 else 0.0
                    date_scores.append(score)

        # ── attribute completeness ────────────────────────────────────────
        if entity_type == "MEDICINE":
            completeness_scores.append(
                medicine_attribute_completeness(relations)
            )
        elif entity_type in {"PROBLEM", "TEST"}:
            # These should at least have assertion + temporality
            has_assert = assertion in VALID_ASSERTIONS
            has_temp   = temporality in VALID_TEMPORALITIES
            completeness_scores.append(1.0 if (has_assert and has_temp) else 0.5 if (has_assert or has_temp) else 0.0)

    # ── compute rates ─────────────────────────────────────────────────────
    def rate(counter: dict, keys: list) -> dict:
        result = {}
        for k in keys:
            total, errors = counter.get(k, [0, 0])
            result[k] = round(errors / total, 4) if total > 0 else 0.0
        return result

    entity_type_error_rate = rate(type_counts, list(VALID_ENTITY_TYPES))
    assertion_error_rate   = rate(assert_counts, ["POSITIVE", "NEGATIVE", "UNCERTAIN"])
    temporality_error_rate = rate(temp_counts, ["CURRENT", "CLINICAL_HISTORY", "UPCOMING", "UNCERTAIN"])
    subject_error_rate     = rate(subj_counts, ["PATIENT", "FAMILY_MEMBER"])

    event_date_accuracy    = round(
        sum(date_scores) / len(date_scores), 4
    ) if date_scores else 1.0

    attribute_completeness = round(
        sum(completeness_scores) / len(completeness_scores), 4
    ) if completeness_scores else 0.0

    return {
        "entity_type_error_rate": entity_type_error_rate,
        "assertion_error_rate":   assertion_error_rate,
        "temporality_error_rate": temporality_error_rate,
        "subject_error_rate":     subject_error_rate,
        "event_date_accuracy":    event_date_accuracy,
        "attribute_completeness": attribute_completeness,
        "_meta": {
            "total_entities":  len(records),
            "noise_entities":  noise_count,
            "date_samples":    len(date_scores),
            "medicine_samples": len([s for s in completeness_scores]),
        }
    }

# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 3:
        print("Usage: python test.py <input.json> <output.json>")
        sys.exit(1)

    input_path  = sys.argv[1]
    output_path = sys.argv[2]

    print(f"Loading: {input_path}")
    records = load_json(input_path)

    if not isinstance(records, list):
        print("Error: input JSON must be a list of entity records.")
        sys.exit(1)

    print(f"Evaluating {len(records)} entities...")
    result = evaluate(records)

    file_name = os.path.basename(input_path)
    output = {"file_name": file_name, **result}

    save_json(output, output_path)
    print(f"Output written to: {output_path}")

    # Print summary to console
    print("\n── Entity Type Error Rates ──────────────────────")
    for k, v in sorted(result["entity_type_error_rate"].items(), key=lambda x: -x[1]):
        bar = "█" * int(v * 20)
        print(f"  {k:<20} {v:.2%}  {bar}")

    print("\n── Assertion Error Rates ────────────────────────")
    for k, v in result["assertion_error_rate"].items():
        print(f"  {k:<20} {v:.2%}")

    print("\n── Temporality Error Rates ──────────────────────")
    for k, v in result["temporality_error_rate"].items():
        print(f"  {k:<20} {v:.2%}")

    print(f"\n── Event Date Accuracy:    {result['event_date_accuracy']:.2%}")
    print(f"── Attribute Completeness: {result['attribute_completeness']:.2%}")
    print(f"\n── Noise entities filtered: {result['_meta']['noise_entities']}/{result['_meta']['total_entities']}")


if __name__ == "__main__":
    main()
