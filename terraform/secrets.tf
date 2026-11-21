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
    name = "secrets"
    # NON-FUNCTIONAL placeholder committed so `terraform validate`'s
    # file() call succeeds in CI before real secrets exist -- the bytes
    # here are not valid KMS ciphertext and `apply`/`plan` will fail
    # against them for real. Melvyn: `make encrypt` with your own awsume
    # session replaces this with the genuine encrypted file -- see
    # README.md's Setup section and terraform/secrets.yaml.example.
    payload = file("secrets.yaml.encrypted")

    context = {
      target = "aws-idc-pim"
    }
  }
}

locals {
  secrets = yamldecode(data.aws_kms_secrets.secrets.plaintext["secrets"])
}
