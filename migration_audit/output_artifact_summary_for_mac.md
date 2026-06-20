# Output Artifact Summary For Mac

Most `structural_compounding_lab/output/*` directories are **generated courts**, not source code.

Recommended rule:

- keep the code, configs, docs, tests, and small helper scripts in Git
- do not try to force every historical output directory through GitHub
- rebuild the key courts on Mac using `migration_audit/artifact_rebuild_chain.csv` and verify against `migration_audit/expected_rebuild_verification_targets.json`
- preserve only small smoke or fixture outputs if they are genuinely useful for tests or UI empty states

This keeps the migration GitHub-safe and avoids committing large historical ledgers unnecessarily.
