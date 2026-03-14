# Clinical AI Pipeline — Evaluation Framework

## Repository Structure
```
├── test.py              # Main evaluation entry point
├── report.md            # Full evaluation report with findings
├── output/
│   └── 336W08434_J721-109845_20241127.json  # Evaluation output
└── README.md
```

## Usage
```bash
python test.py <input.json> <output.json>
```

## What it evaluates
- Entity Type Error Rate (10 types)
- Assertion Error Rate (POSITIVE / NEGATIVE / UNCERTAIN)
- Temporality Error Rate (CURRENT / CLINICAL_HISTORY / UPCOMING / UNCERTAIN)
- Subject Error Rate (PATIENT / FAMILY_MEMBER)
- Event Date Accuracy
- Attribute Completeness

## Key Findings (single file)
- 32.2% of entities are admin/billing noise — should never have been extracted
- PROCEDURE type error rate: 51.7%
- IMMUNIZATION type error rate: 100%
- Event date accuracy: 0% (systematic year derivation bug)
- Subject attribution: 100% correct
- Medicine attribute completeness: 77.1%
