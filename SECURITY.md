# Security Policy

## Reporting Security Vulnerabilities

If you discover a security vulnerability in this project, please report it responsibly:

### How to Report

- **Email**: [security@mdekort.nl](mailto:security@mdekort.nl)
- **Subject**: `[SECURITY] aws-idc-pim vulnerability report`

### What to Include

Please provide the following information:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact assessment
- Suggested remediation (if known)

### Response Timeline

- **Acknowledgment**: Within 48 hours
- **Initial assessment**: Within 1 week
- **Resolution**: Depends on severity and complexity

## Security Considerations

### ⚠️ Important Disclaimers

This repository contains code for personal use. Users should be aware:

- **No warranty**: Code provided "as is" without security guarantees
- **Review required**: Always review code before deployment
- **Environment-specific**: Adapt security settings for your use case
- **Credentials**: Never commit secrets or credentials to version control

### This project's specific attack surface

- The Lambda Function URL is public (`authorization_type = "NONE"`) because Discord
  cannot sign requests with IAM SigV4 -- every request is instead verified against
  Discord's Ed25519 signature before any payload field is trusted
  (`aws_idc_pim/discord_verify.py`). A request that fails verification is rejected
  with 401 before touching any AWS API.
- `ALLOWED_DISCORD_USERS` is a hard allow-list checked before any AWS call. A
  verified-but-unlisted Discord user is refused, not just logged.
- This bot can grant `AdministratorAccess` on AWS accounts, including the
  organization's management account (via a narrow, separately-scoped
  cross-account role). Treat the Discord bot token, application credentials, and
  this repo's own deploy pipeline as equivalent in sensitivity to management-account
  admin credentials.

## Supported Versions

Security updates are provided for:

| Version | Supported |
|---------|-----------|
| Latest  | ✅        |
| Previous| ❌        |

Only the latest version receives security updates. Please ensure you're using the most recent version.
