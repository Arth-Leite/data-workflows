output "aws_account_id" {
  value = data.aws_caller_identity.me.account_id
}

output "aws_role_name" {
  value = aws_iam_role.billing.name
}

output "billing_role_arn" {
  value = aws_iam_role.billing.arn
}

output "other_role_arn" {
  value = aws_iam_role.other.arn
}
