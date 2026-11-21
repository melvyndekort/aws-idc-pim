management_account_id    = "075673041815"
root_elevation_role_arn  = "arn:aws:iam::075673041815:role/IdcPimRootElevationRole"
default_duration_minutes = 15
log_level                = "INFO"

target_accounts = {
  management      = "075673041815"
  hermes-agent    = "520519513359"
  network-monitor = "844347863910"
}

# Melvyn's Discord user ID (from the #aws Discord thread) -> his IAM
# Identity Center username, confirmed live via identitystore:ListUsers.
allowed_discord_users = {
  "1164876958895718420" = "melvyn@mdekort.nl"
}
