variable "application" {
  description = "Name used for billing and other tracking/identification purposes"
  type        = string
  default     = "aidlc"

  validation {
    condition     = can(regex("^[a-z0-9-]{1,10}$", var.application))
    error_message = "application must match [a-z0-9-]{1,10}, matching the CloudFormation templates."
  }
}

variable "environment" {
  description = "Name of the deployment branch"
  type        = string
  default     = "main"

  validation {
    condition     = can(regex("^[a-z0-9]{1,4}$", var.environment))
    error_message = "environment must match [a-z0-9]{1,4} -- four characters, no hyphens, as in every template here."
  }
}

variable "owner" {
  description = "Who owns this deployment (cornell:owner)"
  type        = string
  default     = "ai-sei"
}

variable "blueprint_version" {
  description = "Version of the entra-probe blueprint (cornell:blueprint-version). Bumped in the PR that changes the blueprint."
  type        = string
  default     = "0.1.0"
}

locals {
  deployment_id = "${var.application}-${var.environment}-entra-probe"

  # Entra applications take a flat list of strings, not key/value pairs -- there is no
  # equivalent of an AWS tag set on this resource type. The four required cornell:* values are
  # therefore encoded as "key=value" strings, which keeps them greppable via Graph
  # ($filter=tags/any(t:t eq '...')) even though the shape differs from every CloudFormation
  # resource in this repo. See this blueprint's README.
  cornell_tags = [
    "cornell:owner=${var.owner}",
    "cornell:blueprint=entra-probe",
    "cornell:blueprint-version=${var.blueprint_version}",
    "cornell:deployment-id=${local.deployment_id}",
  ]
}

# The smallest real, idempotent thing the Entra path can create. Its purpose is to prove the
# chain end to end -- Secrets Manager -> provider auth -> S3 state -> apply -- the same way
# the hello-world bucket proves the CloudFormation path.
#
# Deliberately grants nothing: no required_resource_access, no credentials, no service
# principal. It is a directory object and nothing can authenticate as it.
resource "azuread_application" "probe" {
  display_name     = local.deployment_id
  description      = "AI-DLC workshop: proves the Terraform-from-CodeBuild path reaches the tenant. Grants nothing and cannot be authenticated as."
  sign_in_audience = "AzureADMyOrg"
  tags             = local.cornell_tags

  # Terraform would otherwise adopt whatever owner the calling principal happens to be and
  # show a diff whenever that changes.
  lifecycle {
    ignore_changes = [owners]
  }
}

output "application_object_id" {
  description = "Directory object id of the probe application"
  value       = azuread_application.probe.object_id
}

output "application_client_id" {
  description = "Application (client) id of the probe application"
  value       = azuread_application.probe.client_id
}

output "deployment_id" {
  description = "Value encoded in the cornell:deployment-id tag"
  value       = local.deployment_id
}
