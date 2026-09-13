# Task Packet Template

> Reusable template for scoping individual tasks for AI agents or human implementers.

---

## <TASK-ID>: <Descriptive Title>

### OBJECTIVE
One sentence: what this task accomplishes.

### ALLOWED FILES
- `path/to/file.py` — modify
- `path/to/new_file.py` — create
- `path/to/test.py` — test

### FORBIDDEN FILES
- `path/to/system/config.php` — do not touch
- `path/to/production/db.php` — do not touch

### CONTEXT / PRE-REQUISITES
What must be true before this task starts. Reference previous task IDs.

### ACCEPTANCE CRITERIA
1. Criterion 1 — measurable
2. Criterion 2 — testable
3. Criterion 3 — verifiable in the running system

### TESTS REQUIRED
- Unit test for X function
- Integration test for Y endpoint
- Manual smoke: verify Z works in console

### IMPLEMENTATION NOTES
- WIM model namespace to use (wim_* tables)
- API route pattern to follow
- Specific pattern to match (existing code reference)

### ESCALATION CONDITIONS
- If X happens, stop and escalate
- If Y is unclear, ask before proceeding

### EVIDENCE REQUIRED
- Output of DB query creating data
- API request/response for endpoint
- Screenshot of console if applicable