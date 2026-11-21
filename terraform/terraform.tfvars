management_account_id    = "075673041815"
root_elevation_role_arn  = "arn:aws:iam::075673041815:role/IdcPimRootElevationRole"
default_duration_minutes = 15
log_level                = "INFO"

target_accounts = {
  management      = "075673041815"
  hermes-agent    = "520519513359"
  network-monitor = "844347863910"
}

# Empty on purpose -- see variables.tf. Fill in once the Discord
# Application exists and Melvyn provides his Discord user ID.
allowed_discord_users = {}
