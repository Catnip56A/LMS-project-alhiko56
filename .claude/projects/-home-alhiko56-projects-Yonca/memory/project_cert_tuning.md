---
name: project-cert-tuning
description: Per-course certificate x/y tuning — DONE. JSON file + admin UI implemented.
metadata:
  type: project
---

Implemented 2026-06-21. Per-course certificate overlay tuning is now live.

**Files:**
- `yonca/static/certificates/tuning.json` — stores `"default"` key plus per-course keys by course_id (string)
- `yonca/certificate_generator.py` — `load_tuning(course_id)` merges defaults → file default → per-course override; `save_tuning(course_id, values)` persists to JSON
- `yonca/admin/__init__.py` — `CertificateTuningView` registered as "Certificate Tuning" admin panel entry
- `yonca/templates/admin/certificate_tuning.html` — form with course selector; JS populates fields on course change; table showing all current values

**How to apply:** Task is complete. If per-course columns appear in the admin table, the feature is working. Saving clears cached PNG/PDF files for affected certs so they regenerate on next view.