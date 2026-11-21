# aws-idc-pim

Discord-driven just-in-time elevation for IAM Identity Center permission sets.

No standing `AdministratorAccess` assignment. `/elevate target:<account> duration:<minutes>`
grants it temporarily (default 15 minutes) and schedules an automatic revoke;
`/revoke target:<account>` ends it early. See `CLAUDE.md` for the architecture and
`Tech/Homelab/planning/aws-idc-pim-2026-11-20.md` (Obsidian vault) for the full design
rationale.

## Setup

1. `tf-aws` and `tf-github` prerequisites (subaccount, delegated IAM Identity Center
   administration, OIDC roles) are already applied -- see `CLAUDE.md`'s Related Repositories.
2. `make apply` once with placeholder secrets to provision the Lambda Function URL.
3. `terraform -chdir=terraform output function_url` -- register that as the Discord
   Application's Interactions Endpoint URL (Discord Developer Portal -> your app ->
   General Information).
4. Fill in real values in `terraform/secrets.yaml` (copy from `terraform/secrets.yaml.example`),
   `make encrypt`, commit the resulting `terraform/secrets.yaml.encrypted`, `make apply` again.
5. Set `allowed_discord_users` in `terraform/terraform.tfvars` to your real Discord user ID,
   `make apply`.
6. Register the `/elevate` and `/revoke` slash commands with Discord (not yet automated here).

## Usage

```bash
make test
make plan
make apply
make deploy   # pushes real Lambda code via aws lambda update-function-code
```

See `SECURITY.md` for this bot's attack surface and intended blast radius.
