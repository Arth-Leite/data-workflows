variable "project_id" {
  type    = string
  default = "dataops-case-study-509018"
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "my_ip" {
  type        = string
  description = "My public IP as a CIDR block"

  validation {
    condition     = can(cidrnetmask(var.my_ip))
    error_message = "my_ip must be a CIDR block"
  }
}

variable "aws_account_id" {
  type        = string
  description = "AWS account the billing service runs in"

  validation {
    condition     = can(regex("^[0-9]{12}$", var.aws_account_id))
    error_message = "aws_account_id must be 12 digits"
  }
}

variable "aws_role_name" {
  type        = string
  description = "AWS IAM role the billing service runs as (name only, without path)"

  validation {
    condition     = can(regex("^[\\w+=,.@-]{1,64}$", var.aws_role_name))
    error_message = "aws_role_name must be a valid IAM role name"
  }
}
