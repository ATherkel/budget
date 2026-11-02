# Prototype lint exception — approved 29 September 2026

The owner explicitly approved the exact three-file INP001/CPY001 exceptions
below while authorizing artifact publication. They are now applied in
pyproject.toml. No other rule or threshold changed. The original proposal and
reasoning are retained below as history.

🤖 Added by Codex (GPT-6 Astra)

## Original proposal

No configuration has been changed. The locked Ruff 0.16.8 reports exactly
INP001 and CPY001 on the three prototype scripts. The functional, formatting,
type and complexity checks pass. Adding an __init__.py fixes INP001 but makes
the preserved dashboard-11 folder fail N999 (invalid Python package name).

Proposal: add these exact entries under the existing
`[tool.ruff.lint.per-file-ignores]` table in `pyproject.toml`:

```toml
# Throwaway dashboard scripts retain their established non-package launch paths.
# INP001: standalone prototype scripts, deliberately not an importable package.
# CPY001: no copyright notice is invented for the prototype; licensing is unchanged.
"prototypes/dashboard-11/serve.py" = ["INP001", "CPY001"]
"prototypes/dashboard-11/build_example.py" = ["INP001", "CPY001"]
"prototypes/dashboard-11/check_fixtures.py" = ["INP001", "CPY001"]
```

All other rules remain enabled, including every rule for production code.
Alternative: retain the findings until a repository-wide copyright/package
convention is chosen. The prototype remains runnable either way.

Approval is required by `docs/agents/code-quality.md`: "Never edit the tool
configuration, raise a threshold, add a rule to an ignore list, or add a
suppression ... without the owner's explicit approval in the task."
