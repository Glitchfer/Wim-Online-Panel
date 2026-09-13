# Definition of Done — WIM Online

A feature is **Done** when ALL of the following are true:

## Acceptance criteria met
- All acceptance criteria defined for the task pass
- Feature behaves as specified in SCOPE.md
- Edge cases handled (empty state, error state, boundary values)

## Tests pass
- Unit tests written for new logic (PHPUnit for API, JS tests for frontend)
- Integration tests pass for API endpoints
- Manual smoke test of the feature in the actual environment

## No regression
- Existing tests still pass
- Existing features still work (manual check of adjacent features)
- No console errors or warnings introduced

## Data integrity verified
- If feature creates/modifies data: verify the data in DB matches expected shape
- If feature involves geofence events: verify events logged correctly
- If feature involves orders: verify order links to visit event

## Code quality
- No dead code, commented-out code, or debug logging
- No hardcoded values that should be config (use `.env` or config)
- Error messages are user-friendly (Bahasa Indonesia where applicable)
- Follows WIM Online API conventions and patterns

## Documentation
- Any new API endpoints documented
- Any new config/setup steps added to project docs
- TASK-PACKET.md updated if task was agent-executed

## Review
- Self-review: diff checked for unintended changes
- If AI agent executed: spec compliance review + code quality review passed
- No unrelated changes in the commit