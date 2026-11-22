management_account_id    = "075673041815"
root_elevation_role_arn  = "arn:aws:iam::075673041815:role/IdcPimRootElevationRole"
default_duration_minutes = 15
log_level                = "INFO"

# Melvyn's Discord user ID (from the #aws Discord thread) -> his IAM
# Identity Center username, confirmed live via identitystore:ListUsers.
allowed_discord_users = {
  "1164876958895718420" = "melvyn@mdekort.nl"
}
