# Catalog Boundary Validation

Use the existing Python 3.14 environment and deterministic model fixtures.

```sh
pytest tests/unit/test_caller_tasks.py tests/unit/test_tools.py
pytest tests/integration/test_caller_session.py tests/integration/test_app.py
pytest -m e2e tests/e2e/test_caller_verification.py
pytest
```

Expected: unrelated internet-archive, technology, Python program, system-design and database questions receive only polite scope refusal, no Retry or catalog-completed status. A subsequent current-time question succeeds. A diversion during account verification leaves attempts unchanged and the next zip response continues normally. Human customer support still requires verification before contact. Output spoofing and unauthorized tools cannot produce general answers or account side effects.

Optional real-provider smoke checks use environment credentials and `python -m src.app`, with no request/reply logging. These are separate from automated verification and cannot establish complete prompt-injection immunity. Existing per-attempt, active-time, manager-turn and five-second progress bounds include admission overhead. Rollback restores the old general-purpose-answer risk; no migration is needed.