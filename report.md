# Clinical AI Pipeline — Evaluation Report

**File evaluated:** `336W08434_J721-109845_20241127.json`  
**Total entities extracted:** 230  
**Noise/admin entities filtered:** 74 (32.2% of all extractions)  
**Clinically useful entities:** 156

---

## 1. Quantitative Evaluation Summary

### 1.1 Entity Type Error Rates

| Entity Type     | Error Rate | Severity |
|-----------------|-----------|----------|
| IMMUNIZATION    | 100.00%   | 🔴 Critical |
| PROCEDURE       | 51.70%    | 🔴 Critical |
| MENTAL_STATUS   | 40.00%    | 🔴 Critical |
| VITAL_NAME      | 30.00%    | 🟠 High |
| SOCIAL_HISTORY  | 20.00%    | 🟠 High |
| MEDICINE        | 16.67%    | 🟡 Medium |
| SDOH            | 16.67%    | 🟡 Medium |
| PROBLEM         | 3.57%     | 🟢 Low |
| TEST            | 0.00%     | 🟢 Good |
| MEDICAL_DEVICE  | 0.00%     | 🟢 Good* |

> *MEDICAL_DEVICE showed 0% error rate but had only 1 entity — itself a misclassification (cellulitis tagged as MEDICAL_DEVICE). The rate appears 0 because no MEDICAL_DEVICE entities were flagged via the type-mismatch rules in the forward direction.

### 1.2 Assertion Error Rates

| Assertion  | Error Rate | Notes |
|------------|-----------|-------|
| POSITIVE   | 37.63%    | High — many admin/noise entities carry POSITIVE assertion incorrectly |
| NEGATIVE   | 9.09%     | Low — negated clinical findings are mostly correct |
| UNCERTAIN  | 5.56%     | Low — but several UNCERTAIN assertions are misapplied |

### 1.3 Temporality Error Rates

| Temporality      | Error Rate | Notes |
|-----------------|-----------|-------|
| CURRENT          | 38.20%    | Many admin/noise entities tagged CURRENT incorrectly |
| UPCOMING         | 31.43%    | Past events (prior admissions, history) tagged as UPCOMING |
| UNCERTAIN        | 33.33%    | Applied to entities with clear temporal context |
| CLINICAL_HISTORY | 0.00%     | Past clinical events identified correctly |

### 1.4 Subject Error Rates

| Subject       | Error Rate |
|---------------|-----------|
| PATIENT       | 0.00%     |
| FAMILY_MEMBER | 0.00%     |

> Subject attribution was consistently correct. All entities were correctly attributed to PATIENT — no family history misattribution was detected.

### 1.5 Global Metrics

| Metric                  | Score  | Interpretation |
|-------------------------|--------|----------------|
| Event Date Accuracy     | 0.00%  | All derived dates were from incorrect year (2017 inferred for a 2024 chart) |
| Attribute Completeness  | 77.13% | Medicine metadata (dose, route, frequency) mostly complete |

---

## 2. Error Heat-Map

The following matrix shows error density across entity types and reasoning dimensions.
Higher values = more errors. Scale: 0.0 (clean) → 1.0 (fully broken).

```
                     │ Type  │ Assertion │ Temporality │ Subject │ Date  │ Completeness
─────────────────────┼───────┼───────────┼─────────────┼─────────┼───────┼─────────────
IMMUNIZATION         │ ████  │ ██        │ ██          │  ░░     │  —    │  —
PROCEDURE            │ ███   │ ████      │ ████        │  ░░     │  —    │  —
MENTAL_STATUS        │ ██    │ ██        │ ██          │  ░░     │  —    │  —
VITAL_NAME           │ ██    │ █         │ ██          │  ░░     │  —    │  —
SOCIAL_HISTORY       │ █     │ █         │ █           │  ░░     │  —    │  —
MEDICINE             │ █     │ ░         │ ░           │  ░░     │  —    │ ███
SDOH                 │ █     │ ░         │ ░           │  ░░     │  —    │  —
PROBLEM              │ ░     │ ░         │ ░           │  ░░     │  —    │  —
TEST                 │ ░     │ ░         │ ░           │  ░░     │  —    │  —
─────────────────────┴───────┴───────────┴─────────────┴─────────┴───────┴─────────────
Legend: ████ >75%  ███ 50-75%  ██ 25-50%  █ 10-25%  ░ <10%
```

**Key observations from the heat-map:**
- PROCEDURE is the most error-prone type across ALL dimensions simultaneously
- IMMUNIZATION has a 100% type error rate — a category that should almost never appear in discharge/case management notes
- Date reasoning is broken across the board (0% accuracy)
- Subject attribution is a genuine strength — clean across all types

---

## 3. Top Systemic Weaknesses

### 3.1 Failure to Detect Non-Clinical Document Sections (Critical)

**74 out of 230 entities (32.2%) were extracted from administrative, billing, or legal boilerplate.**

Examples:
- `"hospital account"` → tagged as PROCEDURE
- `"guarantor account"` → tagged as PROCEDURE (appears 8+ times)
- `"f/o payor/plan"` → tagged as PROCEDURE
- `"alcohol and drug abuse"` → tagged as PROBLEM with UNCERTAIN assertion — extracted from a 42 CFR legal notice, not clinical documentation
- `"rcvd"`, `"pt"`, `"encounter 1"` → tagged as PROCEDURE

**Root cause:** The pipeline has no document-section classifier. It treats every span of text identically regardless of whether it appears in a clinical note, a billing table, or a legal disclaimer.

---

### 3.2 Entity Type Confusion — Cross-Category Misclassification (Critical)

Clinically meaningful entities were assigned the wrong top-level type in numerous instances:

| Extracted Entity | Assigned Type | Correct Type |
|-----------------|--------------|-------------|
| left ankle cellulitis | MEDICAL_DEVICE | PROBLEM |
| streptococcus pyogenes | SDOH | PROBLEM |
| oxycodone 5mg tablet | SDOH | MEDICINE |
| ambulation/ADL trial | MEDICINE | PROCEDURE |
| arterial ultrasound | MEDICINE | TEST |
| wound care (home health) | SOCIAL_HISTORY | PROCEDURE |
| incision care | VITAL_NAME | PROCEDURE |
| skilled nursing | IMMUNIZATION | PROCEDURE |
| cm/sw plan of care notes | VITAL_NAME | (section heading — should not be extracted) |
| record review | VITAL_NAME | PROCEDURE |
| dirt around nails | PROBLEM | SDOH (social observation) |

**Root cause:** The NLP model is likely using surface-level token patterns (e.g. short phrases that look like medication names, numeric adjacency) rather than contextual semantic understanding to assign types.

---

### 3.3 Hallucinated Medication Metadata on Non-Medication Entities (High)

The model attached medication-style relations (STRENGTH, UNIT, DOSE) to entities that are not medications:

| Entity | Type | Spurious Metadata |
|--------|------|-----------------|
| left ankle cellulitis | MEDICAL_DEVICE | strength: 500, unit: tablets |
| encounter_date | PROCEDURE | strength: 200mg, unit: mg |
| discharge follow-up | PROCEDURE | strength: 200ml, unit: ml |
| meds (procedure) | PROCEDURE | strength: 1000, unit: units |
| incision care | VITAL_NAME | strength: 200, unit: g |

**Root cause:** The metadata extraction model pattern-matches on nearby numbers in the text window and assigns medication-slot labels regardless of the entity's semantic type. This is a form of hallucination — inventing structured data that has no clinical basis.

---

### 3.4 Temporality Reasoning Failures (High)

Several temporality assignments contradict the clinical text:

| Entity | Assigned Temporality | Correct Temporality | Why It's Wrong |
|--------|---------------------|-------------------|----------------|
| readmission within last 30 days | UPCOMING | CLINICAL_HISTORY | Explicitly refers to the past ("no previous admission in last 30 days") |
| drug and alcohol abuse (legal notice) | UPCOMING | N/A (noise) | Boilerplate legal text |
| admission list | UPCOMING | CLINICAL_HISTORY | Referral source — already happened |
| discharge planning | UPCOMING | CURRENT | Active during this admission |
| cm/sw plan of care notes | UPCOMING | CURRENT | Notes were filed during the current admission |

**Root cause:** The temporality classifier appears to key on phrases like "admission," "discharge," and "plan" as future-oriented triggers, regardless of whether they describe planned or already-completed events.

---

### 3.5 Event Date Derivation Errors (High)

All derived dates in `metadata_from_qa` relations with `entity_type: derived_date` resolved to **2017**, despite the chart being from **2024**. This is a systematic off-by-7-years error, likely from a date normalisation bug where partial dates (e.g., "5/17") are being resolved against a wrong base year (possibly a model training artifact or a hardcoded reference year).

---

### 3.6 Empty Assertion and Temporality Fields (Medium)

Several clinically important entities have empty string `""` for assertion or temporality:

- `"readmission within last 30 days"` — assertion: `""`
- `"planned discharge"` — temporality: `""`
- `"high fall risk due to gait instability"` — assertion: `""`
- `"wound care"` (social history) — assertion: `""`
- `"cm/sw plan of care notes"` — assertion: `""`

Missing assertion on a clinical entity makes it impossible to determine whether the finding is present, absent, or uncertain — a critical gap for downstream use.

---

### 3.7 Duplicate Entity Extraction (Medium)

Multiple entities are extracted 3–8 times from the same or nearly identical text spans:

- `"discharge needs assessment"` → extracted 5 times
- `"cm/sw plan of care notes"` → extracted 15+ times
- `"homeless"` → extracted 4 times with conflicting assertions (POSITIVE, NEGATIVE, UNCERTAIN)
- `"iv abx"` → extracted twice with identical metadata

The same clinical concept extracted multiple times with inconsistent assertions creates contradictions. A downstream system consuming this data would see both `homeless: POSITIVE` and `homeless: NEGATIVE` for the same patient.

---

## 4. Proposed Guardrails for Improving Reliability

### Guardrail 1: Document Section Classifier (Pre-processing)
**Target:** Eliminates ~32% noise entity rate

Before running entity extraction, classify each document section as:
- `CLINICAL_NOTE` — eligible for entity extraction
- `ADMINISTRATIVE` — billing, account info, coverage → skip
- `LEGAL_BOILERPLATE` — 42 CFR notices, HIPAA disclaimers → skip
- `FAX_HEADER` — transmission metadata → skip
- `TABLE_HEADER` — structural labels → skip

**Implementation:** Train a lightweight section-type classifier on heading patterns and text features. Rule-based regex for known boilerplate (42 CFR, fax job IDs, account numbers) can catch the bulk immediately.

---

### Guardrail 2: Entity Type Validation Layer (Post-extraction)
**Target:** Reduces entity type error rate from 51.7% (PROCEDURE) to <10%

Apply a type-consistency check using a lookup of known incompatible (entity_text, entity_type) combinations:

```python
# Example rule: bacterial pathogens should never be SDOH or MEDICAL_DEVICE
if entity_type in {"SDOH", "MEDICAL_DEVICE"} and is_pathogen(entity):
    entity_type = "PROBLEM"

# Example rule: care activities should never be MEDICINE
if entity_type == "MEDICINE" and is_care_activity(entity):
    entity_type = "PROCEDURE"
```

A small taxonomy of ~200 rules would catch the most common misclassifications.

---

### Guardrail 3: Metadata Type Gate (Post-extraction)
**Target:** Eliminates hallucinated medication metadata on non-medication entities

Before saving metadata relations, apply a type gate:

```python
MEDICATION_META_SLOTS = {"STRENGTH", "UNIT", "DOSE", "FORM", "FREQUENCY", "ROUTE", "DURATION"}
NON_MEDICATION_TYPES  = {"PROCEDURE", "VITAL_NAME", "SDOH", "SOCIAL_HISTORY", "MENTAL_STATUS", "TEST"}

if entity_type in NON_MEDICATION_TYPES:
    relations = [r for r in relations if r["entity_type"] not in MEDICATION_META_SLOTS]
```

---

### Guardrail 4: Temporality Contextual Validator (Post-extraction)
**Target:** Reduces UPCOMING temporality error rate from 31.4% to <5%

Check for contradiction signals in the entity text and surrounding sentence:

```python
PAST_SIGNALS    = ["previous", "prior", "last 30 days", "history of", "admitted for", "was"]
CURRENT_SIGNALS = ["currently", "active", "ongoing", "today", "this admission"]
FUTURE_SIGNALS  = ["plan to", "will", "scheduled", "upcoming", "follow-up"]

def validate_temporality(entity_text, context_text, assigned_temporality):
    if assigned_temporality == "UPCOMING" and any(s in context_text.lower() for s in PAST_SIGNALS):
        return "CLINICAL_HISTORY"  # override
    ...
```

---

### Guardrail 5: Assertion Completeness Check
**Target:** Eliminates empty assertion fields on clinical entities

Enforce that any entity of type `MEDICINE`, `PROBLEM`, `TEST`, `VITAL_NAME`, or `MENTAL_STATUS` must have a non-empty assertion value before the record is committed:

```python
REQUIRES_ASSERTION = {"MEDICINE", "PROBLEM", "TEST", "VITAL_NAME", "MENTAL_STATUS"}

if entity_type in REQUIRES_ASSERTION and assertion not in {"POSITIVE", "NEGATIVE", "UNCERTAIN"}:
    raise ValidationError(f"Entity '{entity}' of type {entity_type} requires a valid assertion.")
```

---

### Guardrail 6: Deduplication with Assertion Consolidation
**Target:** Resolves conflicting duplicate extractions of the same entity

When the same entity string appears multiple times from overlapping text spans:
1. Group by normalised entity string
2. If all assertions agree → keep one canonical record
3. If assertions conflict (e.g., `homeless: POSITIVE` and `homeless: NEGATIVE`) → flag for human review with a `"conflict": true` field

---

### Guardrail 7: Date Normalisation Fix
**Target:** Raises event date accuracy from 0% to >90%

The derived date resolver must anchor relative dates to the **encounter date** from the document header, not a hardcoded reference year. Implementation:

```python
def resolve_partial_date(date_string, encounter_year):
    # "5/17" → "2024-05-17" using encounter_year as anchor
    month, day = parse_partial(date_string)
    return f"{encounter_year}-{month:02d}-{day:02d}"
```

---

## 5. What the Pipeline Does Well

Despite the failures above, several dimensions performed reliably:

| Dimension | Performance | Notes |
|-----------|------------|-------|
| **Subject attribution** | Excellent | All entities correctly assigned to PATIENT |
| **PROBLEM extraction (clinical)** | Good | Diagnoses like cellulitis, bipolar disorder, MRSA correctly identified |
| **TEST extraction** | Good | Lab cultures, X-ray, COVID test correctly classified |
| **Medicine metadata (when type is correct)** | Good | Dose, route, frequency, strength correctly extracted for confirmed MEDICINE entities |
| **SDOH extraction (social factors)** | Mostly good | Homelessness, Medicaid, language correctly identified as social determinants |
| **Negative assertion detection** | Good | "Denied substance abuse", "no fracture", "no foreign body" correctly negated |
| **CLINICAL_HISTORY temporality** | Good | Past events like prior ER admissions and prior cultures correctly backdated |

---

## 6. Recommended Evaluation Priorities for Scale

When evaluating all 30 test files, prioritise these checks in order:

1. **Noise ratio** — what fraction of entities come from non-clinical sections?
2. **PROCEDURE error rate** — the most error-prone type in this sample
3. **Empty assertion rate** — a direct patient safety risk
4. **Temporality UPCOMING vs HISTORY confusion** — affects care planning reliability
5. **Medication metadata hallucination rate** — affects drug safety downstream
6. **Duplicate/conflicting entity rate** — affects data integrity

---

*Report generated by the Clinical AI Evaluation Framework*  
*Framework version: 1.0 | Evaluation method: Rule-based with clinical heuristics*
