#!/usr/bin/env bash
# Usage: source assume.sh <role-arn>
# Exports temporary credentials for the role; the Google auth library reads them from env vars
creds=$(aws sts assume-role --role-arn "$1" --role-session-name wif-test \
  --query 'Credentials.[AccessKeyId,SecretAccessKey,SessionToken]' --output text) || return 1
read -r AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN <<<"$creds"
export AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
export AWS_REGION=eu-west-1
aws sts get-caller-identity --query Arn --output text
