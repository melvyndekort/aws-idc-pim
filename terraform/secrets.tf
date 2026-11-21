# KMS-encrypted secrets, same pattern as every other repo
# (terraform/secrets.yaml.encrypted, decrypted via data.aws_kms_secrets).
#
# NOT populated yet: Melvyn creates the Discord Application once this
# Lambda's Function URL is live (needs the URL to register the Interactions
# Endpoint). Until then, terraform/secrets.yaml.encrypted holds placeholder
# values -- `make encrypt` after filling in the real ones once the Discord
# app exists. See Tech/Homelab/planning/aws-idc-pim-2026-11-20.md.
data "aws_kms_secrets" "secrets" {
  secret {
    name    = "secrets"
    payload = file("secrets.yaml.encrypted")

    context = {
      target = "aws-idc-pim"
    }
  }
}

locals {
  secrets = yamldecode(data.aws_kms_secrets.secrets.plaintext["secrets"])
}
