terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

provider "aws" {
  region = "eu-west-1"
}

# Whoever runs terraform is also the one who assumes the roles in the test
data "aws_caller_identity" "me" {}

data "aws_iam_policy_document" "trust_me" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [data.aws_caller_identity.me.arn]
    }
  }
}

# The role GCP trusts; no permission policy, GetCallerIdentity is always allowed
resource "aws_iam_role" "billing" {
  name               = "billing-orchestrator"
  assume_role_policy = data.aws_iam_policy_document.trust_me.json

  lifecycle {
    precondition {
      condition     = !endswith(data.aws_caller_identity.me.arn, ":root")
      error_message = "Run as an IAM user, not root: root can't assume roles"
    }
  }
}

# Same account, different role: GCP must refuse it
resource "aws_iam_role" "other" {
  name               = "other-role"
  assume_role_policy = data.aws_iam_policy_document.trust_me.json
}
