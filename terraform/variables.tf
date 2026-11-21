variable "management_account_id" {
  description = "AWS account ID of the organization's management account"
  type        = string
  default     = "075673041815"
}

variable "root_elevation_role_arn" {
  description = "Narrow management-account role this bot assumes for requests targeting the management account itself (tf-aws's management/identity-center-pim-root-role.tf)"
  type        = string
  default     = "arn:aws:iam::075673041815:role/IdcPimRootElevationRole"
}

variable "target_accounts" {
  description = "Discord command `target` name -> AWS account ID. A new workload account needs no code change, only an entry here."
  type        = map(string)
  default = {
    management      = "075673041815"
    hermes-agent    = "520519513359"
    network-monitor = "844347863910"
  }
}

variable "default_duration_minutes" {
  description = "Elevation duration when /elevate is called without an explicit duration"
  type        = number
  default     = 15
}

variable "log_level" {
  description = "Log level for the Lambda function"
  type        = string
  default     = "INFO"
}

variable "allowed_discord_users" {
  description = <<-EOT
    Discord user ID -> email, Terraform-managed allow-list. The Lambda
    refuses any command from a Discord user not listed here before
    touching AWS at all. Defaults to empty (nobody authorized) until
    Melvyn creates the Discord Application and provides real IDs -- see
    Tech/Homelab/planning/aws-idc-pim-2026-11-20.md.
  EOT
  type        = map(string)
  default     = {}
}
