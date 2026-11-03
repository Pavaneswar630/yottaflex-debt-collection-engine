"""Count valid near-miss labels that blind detectors flagged (reporting only)."""
import csv
import sys

GT = "ground_truth/full/ground_truth.csv"
DET = "reports/detections.csv"


def rows(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


gt, det = rows(GT), rows(DET)
detected = {v for r in det for v in r.values() if v}
near = [r for r in gt if any("near" in (v or "").lower() for v in r.values())]
if not near:
    sys.exit("No near-miss rows found; inspect the issue_type column in " + GT)

id_cols = [c for c in near[0] if c.endswith("_id")]
flagged = sum(any(r[c] in detected for c in id_cols if r[c]) for r in near)
print(f"Near-miss rows: {len(near)}; flagged by detectors: {flagged}")