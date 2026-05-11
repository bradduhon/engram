locals {
  account_id  = data.aws_caller_identity.current.account_id
  region      = data.aws_region.current.region
  aws_profile = var.aws_profile
}
