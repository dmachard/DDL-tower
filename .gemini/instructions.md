# Project Rules - DDLtower

## Mandatory Testing
After any code modification, you MUST run the full test suite to ensure no regressions:
`docker compose exec -T ddltower python3 -m pytest -p no:cacheprovider -v app/tests/test*`

## Code Integrity
- Never modify quality scores (`app/core/utils.py`) or library organization logic (`app/services/library_service.py`) without explicit user consent.
- Always verify that new parser rules do not break existing test cases.

## Communications
- Keep responses concise.
- Always report test results after modifications.
