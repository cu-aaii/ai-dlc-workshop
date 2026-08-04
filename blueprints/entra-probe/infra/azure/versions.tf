terraform {
  required_version = "~> 1.15"

  required_providers {
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.9"
    }
  }

  # Partial configuration on purpose. Every value comes from -backend-config flags in
  # pipeline/terraform.yml, so this module deploys unchanged into any environment and the
  # repository carries no account or bucket names.
  backend "s3" {}
}

# Credentials come from ARM_TENANT_ID / ARM_CLIENT_ID / ARM_CLIENT_SECRET, which the provider
# reads natively. They are CodeBuild SECRETS_MANAGER variables, never Terraform variables --
# a Terraform variable would end up in the plan file and in state.
provider "azuread" {}
