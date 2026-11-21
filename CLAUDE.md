# aws-idc-pim

> For global standards, way-of-workings, and pre-commit checklist, see `~/.claude/CLAUDE.md`

## Role

Python developer and AWS engineer.

## What This Does

Discord-driven just-in-time (JIT) elevation for IAM Identity Center's `AdministratorAccessJIT`
permission set -- a dedicated permission set, separate from the standing `AdministratorAccess`
one the aws-users group has everyday access through (a delegated administrator cannot manage
assignments for any permission set that has a standing management-account assignment, in any
account -- see `elevation.py`'s module docstring). No standing admin assignment on this one:
`/aws-elevate target:<account> duration:<minutes>`
grants it temporarily (default 15 min), auto-revoked via a one-time EventBridge Scheduler
rule; `/aws-revoke target:<account>` ends it early. See
`Tech/Homelab/planning/aws-idc-pim-2026-11-20.md` in the Obsidian vault for the full design
rationale (why not AWS's own TEAM solution, why a Lambda Function URL instead of API
Gateway, why delegated administration + one narrow management-account role instead of
one broad role).

## Lambda Deployment Pattern

Terraform creates the Lambda with dummy code and `ignore_changes` on `source_code_hash`.
Actual code is deployed via `make deploy` / CI pipeline using `aws lambda update-function-code`.

## One Lambda, three callers

- Discord's HTTP Interactions endpoint (Function URL, synchronous) -- verifies the Ed25519
  signature, ACKs within Discord's ~3s budget, re-invokes itself asynchronously for the
  real work.
- Its own async self-invocation (`action: process_command`) -- does the actual
  `sso-admin`/`identitystore`/`scheduler` calls and posts the Discord followup.
- EventBridge Scheduler's one-time auto-revoke invocation (`action: scheduled_revoke`).

## Repository Structure

- `aws_idc_pim/` -- Lambda handler source (`handler.py` dispatch, `elevation.py` AWS
  calls, `discord_verify.py` signature check, `discord_api.py` REST calls)
- `tests/` -- Test suite
- `terraform/` -- Lambda, IAM, EventBridge Scheduler roles, Function URL, KMS secrets
- `Makefile` -- `install`, `test`, `lint`, `format`, `package`, `deploy`, `init`, `validate`,
  `plan`, `apply`, `decrypt`, `encrypt`, `update-deps`, `clean`

## Terraform Details

- Backend: S3 key `aws-idc-pim.tfstate` in `mdekort-tfstate-397379012163`
- Providers: AWS `~> 6.19`
- Secrets: KMS context `target=aws-idc-pim`, decrypted cross-account against management's
  `alias/generic` key (see `tf-aws`'s `management/variables.tf` `subaccount_secret_targets`)
- `allowed_discord_users` / `target_accounts` / `default_duration_minutes`: `terraform/variables.tf`

## Manual step not automatable here

`terraform/secrets.yaml.encrypted` (Discord public key, application ID, bot token) must be
created by Melvyn via `make encrypt` -- Hermes can decrypt this repo's secrets via the
cross-account `ReadOnlyRole` but has no `kms:Encrypt` grant on management's key, by design.
See `terraform/secrets.yaml.example` for the required keys and where to find each value in
the Discord Developer Portal (needs this Lambda's Function URL to exist first, to register
as the Interactions Endpoint URL -- apply once with placeholders, create the Discord app,
re-encrypt with real values, re-apply).

## Related Repositories

- `~/src/melvyndekort/tf-aws` -- the `aws-idc-pim` subaccount, delegated IAM Identity
  Center administration, and the narrow `IdcPimRootElevationRole` for management-account
  requests
- `~/src/melvyndekort/tf-github` -- this repo's own registration + OIDC roles
