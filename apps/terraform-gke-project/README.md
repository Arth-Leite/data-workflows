# terraform-gke-project

A small, cost-conscious FastAPI service running on GKE, provisioned end to end with Terraform.

The API stores users in Cloud SQL (Postgres) and logs every request to BigQuery, so usage can be
billed by time of day. An external AWS billing service can read the billing data through Workload
Identity Federation, with no service account keys on either side.

## What it does

- **FastAPI API** with a `GET /`, a `GET /healthz` probe and CRUD endpoints under `/users`.
- **Users in Cloud SQL** using Postgres over a private IP, authenticated with IAM (no passwords).
- **Billing logs in BigQuery**: a middleware writes one JSON line per request to stdout, a log sink
  ships it to a partitioned BigQuery table, and a `prices` view turns it into a bill.
- **Cross-cloud access**: an AWS IAM role can impersonate a GCP service account through Workload
  Identity Federation and read only the billing views.
- **Resilience**: three API replicas, one per zone, behind a PodDisruptionBudget.

## Layout

```
apps/fast-api-hello/   FastAPI app, Dockerfile and the schema migration job
infra/                 Terraform for GKE, Cloud SQL, BigQuery, IAM and Workload Identity
tests/aws-wif/         Terraform stack that plays the AWS billing side
Makefile               build/push the image, apply and destroy the stack
```

## Deploying

Prerequisites: a GCP project with billing enabled, `gcloud`, `terraform`, `docker` and `kubectl`.

Authenticate and select the project, then create `infra/terraform.tfvars` with the AWS side (see
[tests/aws-wif](tests/aws-wif/)):

```hcl
aws_account_id = "<aws-account-id>"
aws_role_name  = "billing-orchestrator"
```

Build and push the image, then apply the stack. `make` reads the project from `gcloud` and derives
the allowed source IP from your current address:

```bash
make push
make apply
```

`make apply` also refreshes `kubectl` credentials, since the cluster endpoint changes whenever the
cluster is recreated. Tear everything down with:

```bash
make destroy
```

Set `PROJECT_ID=...` (or `REGION=...`) to override the defaults. The `my_ip` CIDR is calculated by
the Makefile from `https://checkip.amazonaws.com`; in `infra/terraform.tfvars` you can set it by
hand instead.

## Testing the features

The checks below run against a deployed stack. All of them are read-only apart from the user
lifecycle test, which cleans up after itself.

```bash
API_URL=$(terraform -chdir=infra output -raw fast_api_hello_url)
PROJECT_ID=$(gcloud config get-value project)
```

### API and health probe

Only `/healthz` is excluded from the billing logs, everything else is metered.

```bash
curl "$API_URL"           # "Hello world"
curl "$API_URL/healthz"   # "ok"
```

### User lifecycle

`POST /users` returns a UUID, rejects invalid emails, lower-cases the address and refuses
duplicates. `GET` and `DELETE` return `404` once the user is gone.

```bash
# create, keep the id
curl -sS -X POST "$API_URL/users" -H 'Content-Type: application/json' \
  -d '{"name": "Ada", "email": "Ada@Example.com"}'
# -> 201 {"id":"<uuid>","name":"Ada","email":"ada@example.com","created_at":"..."}

# duplicate email -> 409
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$API_URL/users" \
  -H 'Content-Type: application/json' -d '{"name": "Ada", "email": "ada@example.com"}'

# invalid email -> 422
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$API_URL/users" \
  -H 'Content-Type: application/json' -d '{"name": "Linus", "email": "invalid-email"}'

# read, then delete, then read again -> 404
USER_ID=<uuid-from-the-create-call>
curl -sS "$API_URL/users/$USER_ID"
curl -sS -o /dev/null -w '%{http_code}\n' -X DELETE "$API_URL/users/$USER_ID"   # 204
curl -sS -o /dev/null -w '%{http_code}\n' "$API_URL/users/$USER_ID"             # 404
```

### The API is exposed to a single address

The load balancer only accepts traffic from the configured CIDR. Check the service, and confirm a
request from any other host times out:

```bash
kubectl get svc fast-api-hello -o jsonpath='{.spec.loadBalancerSourceRanges}{"\n"}'
```

### Three replicas spread across zones

The deployment runs one pod per zone and the PodDisruptionBudget keeps two of them available during
upgrades or node drains.

```bash
kubectl get pods -o wide -l app=fast-api-hello -L topology.kubernetes.io/zone
kubectl get pdb fast-api-hello
```

### API calls reach BigQuery

After calling the API a few times, the requests show up in `api_billing.stdout` (about two minutes
after the first request). Only the middleware's JSON lines are there: no uvicorn access logs, no
migration logs and no health probes.

```bash
bq query --use_legacy_sql=false \
  'SELECT timestamp, jsonPayload.method, jsonPayload.path, jsonPayload.status
   FROM api_billing.stdout ORDER BY timestamp'
```

### Billing is time-of-day aware

Prices are in euro cents per hour, in `Europe/Paris`, with `valid_from`/`valid_to` dates so a price
change never rewrites past bills.

```bash
bq query --use_legacy_sql=false \
  'SELECT * FROM api_billing.prices ORDER BY start_hour, valid_from'
```

Only successful `POST`s are billable, joined to the price in force at the time:

```bash
bq query --use_legacy_sql=false "
SELECT COUNT(*) AS billable_calls, SUM(p.price_cents) / 100 AS total_eur
FROM api_billing.stdout c
JOIN api_billing.prices p
  ON DATE(c.timestamp, 'Europe/Paris') >= p.valid_from
 AND DATE(c.timestamp, 'Europe/Paris') <  p.valid_to
 AND EXTRACT(HOUR FROM c.timestamp AT TIME ZONE 'Europe/Paris') >= p.start_hour
 AND EXTRACT(HOUR FROM c.timestamp AT TIME ZONE 'Europe/Paris') <  p.end_hour
WHERE c.jsonPayload.method = 'POST'
  AND c.jsonPayload.status BETWEEN 200 AND 299"
```

### The AWS billing service can read BigQuery only

`tests/aws-wif/` creates two role-less IAM roles: `billing-orchestrator`, which GCP trusts, and
`other-role`, which it must refuse.

```bash
cd tests/aws-wif && terraform init && terraform apply
cd ../..
AWS_ACCOUNT_ID=$(terraform -chdir=tests/aws-wif output -raw aws_account_id)
BILLING_ROLE_ARN=$(terraform -chdir=tests/aws-wif output -raw billing_role_arn)
OTHER_ROLE_ARN=$(terraform -chdir=tests/aws-wif output -raw other_role_arn)
```

Generate the credential file the AWS service would use. It holds no secret, only which pool,
provider and service account to use:

```bash
gcloud iam workload-identity-pools create-cred-config \
  "$(terraform -chdir=infra output -raw aws_billing_wif_provider)" \
  --service-account="aws-billing@$PROJECT_ID.iam.gserviceaccount.com" \
  --aws --output-file=aws-billing-cred.json

export CLOUDSDK_CONFIG=$(mktemp -d)
gcloud auth login --cred-file=aws-billing-cred.json
```

Assume the trusted role and read the billing views:

```bash
source tests/aws-wif/assume.sh "$BILLING_ROLE_ARN"
bq query --use_legacy_sql=false 'SELECT * FROM billing_shared.prices ORDER BY start_hour'
bq query --use_legacy_sql=false 'SELECT * FROM billing_shared.requests ORDER BY timestamp DESC LIMIT 5'
```

It cannot read the raw logs, nor write anything:

```bash
bq query --use_legacy_sql=false 'SELECT * FROM api_billing.stdout LIMIT 1'          # denied
bq query --use_legacy_sql=false 'CREATE TABLE billing_shared.x AS SELECT 1 AS a'    # denied
```

An untrusted role in the same account is rejected at authentication time:

```bash
unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
source tests/aws-wif/assume.sh "$OTHER_ROLE_ARN"
gcloud auth print-access-token    # ERROR: ... rejected by the attribute condition

unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
unset CLOUDSDK_CONFIG
```

Finally, the queries are recorded in the audit logs as the `aws-billing` service account, with the
AWS role behind it:

```bash
gcloud logging read \
  'protoPayload.serviceName="bigquery.googleapis.com" AND protoPayload.authenticationInfo.principalEmail="aws-billing@'"$PROJECT_ID"'.iam.gserviceaccount.com"' \
  --freshness=1h --limit=1 \
  --format='yaml(protoPayload.methodName,protoPayload.authenticationInfo)'
```

## Cost and security notes

- **Cheap by default**: a zonal cluster and a single-zone `db-f1-micro` Cloud SQL instance, spot
  nodes and no public IPs on the nodes.
- **Quota cap**: a project-level `QueryUsagePerDay` preference of 10 GiB keeps BigQuery spending
  inside the free tier.
- **Least privilege**: the API's service account only has DML on `users`, the sink writes as its
  own identity, and the AWS role can read only the `billing_shared` views.
- **No passwords**: Cloud SQL uses IAM authentication and the connector, so there are no database
  credentials to rotate.
