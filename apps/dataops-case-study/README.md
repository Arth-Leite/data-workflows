Hello, my name is Arthur Leite, and this repo is my answer to a DataOps case study.

Each question has been answered without the follow-up questions in mind,
so the implementations of previous questions can be modified through time.

## Verifying the answers

Notes on how I checked each question's requirements after `terraform apply`.

### Q2 - GKE cluster deployed across all zones

```bash
❯ gcloud container clusters list --project=dataops-case-study-509018
NAME                      LOCATION        MASTER_VERSION      MASTER_IP     MACHINE_TYPE  NODE_VERSION        NUM_NODES  STATUS   STACK_TYPE
dataops-cluster  europe-west1-b  1.35.8-gke.1036000  34.53.154.55  e2-micro      1.35.8-gke.1036000  3          RUNNING  IPV4

❯ gcloud container clusters get-credentials dataops-cluster --zone=europe-west1-b --project=dataops-case-study-509018

❯ kubectl config use-context gke_dataops-case-study-509018_europe-west1-b_dataops-cluster

❯ kubectl get nodes -L topology.kubernetes.io/zone
NAME                                                  STATUS   ROLES    AGE    VERSION               ZONE
gke-dataops-cheap-as-possibl-91f494e7-21xc   Ready    <none>   173m   v1.35.8-gke.1036000   europe-west1-b
gke-dataops-cheap-as-possibl-3cd4ebec-r3wz   Ready    <none>   29m    v1.35.8-gke.1036000   europe-west1-c
gke-dataops-cheap-as-possibl-ca6a94b8-4rvf   Ready    <none>   63m    v1.35.8-gke.1036000   europe-west1-d

```

Note: I've tried first with autoscaler bounds but it kept only a single node running since there were no pods pending to trigger the autoscaler, so I've changed to a fixed node count per zone to ensure we respect the "Create the cluster in such that it is deployed in all available zones".

### Q3 - FastAPI hello-world exposed to a single IP

We need to first push the new docker image so that the pod can start.

```bash
gcloud auth configure-docker europe-west1-docker.pkg.dev
# important to choose the platform, otherwise it will push arm
docker build --platform linux/amd64 -t europe-west1-docker.pkg.dev/dataops-case-study-509018/dataops/fast-api-hello:latest apps/fast-api-hello
docker push europe-west1-docker.pkg.dev/dataops-case-study-509018/dataops/fast-api-hello:latest
```

I've got my own IP with ` curl -4 ifconfig.me` and added to `terraform.tfvars`.

```bash
❯ kubectl get pods
NAME                              READY   STATUS    RESTARTS   AGE
fast-api-hello-7f48577f5c-pvrll   1/1     Running   0          7m52s

❯ terraform output
fast_api_hello_url = "http://34.34.184.85"

❯ curl http://34.34.184.85
"Hello world"%
```

I also checked if the app was blocking all IPs except mine, which I could easily verify with [Firewall policies](https://console.cloud.google.com/net-security/firewall-manager/firewall-policies/list?referrer=search&authuser=1&project=dataops-case-study-509018) rules on the GCP Console.

```bash
❯ bat terraform.tfvars
─────┬────────────────────────────────────────
     │ File: terraform.tfvars
─────┼────────────────────────────────────────
   1 │ my_ip = "78.242.185.91/32"
─────┴────────────────────────────────────────

❯ gcloud compute firewall-rules list --project=dataops-case-study-509018 \
  --format="table(name,sourceRanges.list(),allowed[].map().firewall_rule().list():label=ALLOW,denied[].map().firewall_rule().list():label=DENY,priority)"
NAME                                          SOURCE_RANGES                                                 ALLOW                         DENY  PRIORITY
gke-dataops-cluster-1f866ecf-all     10.4.0.0/14                                                   esp,ah,sctp,tcp,udp,icmp            1000
gke-dataops-cluster-1f866ecf-vms     10.0.0.0/20                                                   udp:1-65535,icmp,tcp:1-65535        1000
k8s-41662838684fd66a-node-http-hc             130.211.0.0/22,35.191.0.0/16,209.85.152.0/22,209.85.204.0/22  tcp:10256                           999
k8s-fw-a4b440983d959485889d9c5ad1e5ebee       78.242.185.91/32                                              tcp:80                              999
k8s-fw-a4b440983d959485889d9c5ad1e5ebee-deny  0.0.0.0/0                                                                                   all   1000
```

Note: I bumped the resources on gke from 12GB to 20GB and used e2-small instead of e2-micro. The pods were having a very hard time pulling the image, which took almost 15 min. Although there is a very small increase in price I think it is worth it, the system will be much more reliable, even if we keep our super simple hello world.

### Q4 - FastAPI users endpoints + CloudSQL

First we had to terraform apply. It was necessary then to docker push again, for that I've added `make push` to make the process less manual.

So first we check if the job succeded.
```bash
❯ kubectl get jobs
NAME         STATUS     COMPLETIONS   DURATION   AGE
db-migrate   Complete   1/1           67s        69m
```

Then if the pod is live and running
```bash
❯ kubectl get pods
NAME                              READY   STATUS      RESTARTS   AGE
db-migrate-rdnxk                  0/1     Completed   0          69m
fast-api-hello-859f8866fc-596q8   1/1     Running     0          68m
```

With public IP with `terraform apply` we can get the docs on the browser and check the endpoints and test them.

```bash
❯ curl -X 'GET' 'http://34.156.151.75/'
"Hello world"%

❯ curl -X 'POST' \
  'http://34.156.151.75/users' \
  -H 'accept: */*' \
  -H 'Content-Type: application/json' \
  -d '{
  "name": "string1",
  "email": "user1@example.com"
}'
{"id":1,"name":"string1","email":"user1@example.com","created_at":"2026-09-25T17:19:01.511897Z"}%

❯ curl -X 'POST' \
  'http://34.156.151.75/users' \
  -H 'accept: */*' \
  -H 'Content-Type: application/json' \
  -d '{
  "name": "string2",
  "email": "invalid-email"
}'
{"detail":[{"type":"value_error","loc":["body","email"],"msg":"value is not a valid email address: An email address must have an @-sign.","input":"invalid-email","ctx":{"reason":"An email address must have an @-sign."}}]}%

❯ curl -X 'GET' \
  'http://34.156.151.75/users/1' \
  -H 'accept: */*'
{"id":1,"name":"string1","email":"user1@example.com","created_at":"2026-09-25T17:19:01.511897Z"}%

❯ curl -X 'DELETE' \
  'http://34.156.151.75/users/1' \
  -H 'accept: */*'

❯ curl -X 'DELETE' \
  'http://34.156.151.75/users/1' \
  -H 'accept: */*'
{"detail":"User not found"}%

❯ curl -X 'GET' \
  'http://34.156.151.75/users/1' \
  -H 'accept: */*'
{"detail":"User not found"}%
```

Note on cost: Cloud SQL is not part of the GCP Free Tier, it only offers a 30-day free trial instance, otherwise it is billed (here covered by the $300 welcome credit). Since a managed Postgres was explicitly asked, I went with the cheapest setup possible: `db-f1-micro` shared-core, zonal, 10GB HDD without autoresize, which is enough for the very little traffic expected.

### Q5 - Logging API calls to BigQuery for billing

After `make push` and `make apply` (which now also runs `make refresh` to point `kubectl` at the new cluster), the dataset only holds the `prices` view. The `stdout` table is created by the log sink when the first log arrives.

```bash
❯ kubectl get pods
NAME                              READY   STATUS      RESTARTS   AGE
db-migrate-v8ph2                  0/1     Completed   0          6m46s
fast-api-hello-5844c6dbb5-n49vq   1/1     Running     0          6m9s
```

Then I called every endpoint, with successful and failed POSTs:

```bash
❯ curl -X GET 'http://34.22.179.149/'
"Hello world"

❯ curl -X POST 'http://34.22.179.149/users' -H 'Content-Type: application/json' -d '{"name": "Ada", "email": "ada@example.com"}'
{"id":1,"name":"Ada","email":"ada@example.com","created_at":"2026-09-26T10:08:07.821219Z"}

❯ curl -X POST 'http://34.22.179.149/users' -H 'Content-Type: application/json' -d '{"name": "Grace", "email": "grace@example.com"}'
{"id":2,"name":"Grace","email":"grace@example.com","created_at":"2026-09-26T10:08:08.118495Z"}

❯ curl -X POST 'http://34.22.179.149/users' -H 'Content-Type: application/json' -d '{"name": "Ada", "email": "ada@example.com"}'
{"detail":"A user with this email already exists"}

❯ curl -X POST 'http://34.22.179.149/users' -H 'Content-Type: application/json' -d '{"name": "Linus", "email": "invalid-email"}'
{"detail":[{"type":"value_error","loc":["body","email"],"msg":"value is not a valid email address: An email address must have an @-sign.","input":"invalid-email","ctx":{"reason":"An email address must have an @-sign."}}]}

❯ curl -X GET 'http://34.22.179.149/users/1'
{"id":1,"name":"Ada","email":"ada@example.com","created_at":"2026-09-26T10:08:07.821219Z"}

❯ curl -X DELETE 'http://34.22.179.149/users/2'

❯ curl -X GET 'http://34.22.179.149/users/2'
{"detail":"User not found"}
```

The calls show up in the Logs Explorer, and about 2 minutes later in BigQuery. Only the middleware's JSON lines get there: no uvicorn lines, no `db-migrate` logs and no `/healthz` probes.

```bash
❯ bq ls api_billing
  tableId   Type                Labels                  Time Partitioning      Clustered Fields
 --------- ------- --------------------------------- ------------------------ ------------------
  prices    VIEW    goog-terraform-provisioned:true
  stdout    TABLE                                     DAY (field: timestamp)

❯ bq query --use_legacy_sql=false 'SELECT timestamp, jsonPayload.method, jsonPayload.path, jsonPayload.status FROM api_billing.stdout ORDER BY timestamp'
+---------------------+--------+----------+--------+
|      timestamp      | method |   path   | status |
+---------------------+--------+----------+--------+
| 2026-09-26 10:08:05 | GET    | /        |  200.0 |
| 2026-09-26 10:08:05 | POST   | /users   |  201.0 |
| 2026-09-26 10:08:08 | POST   | /users   |  201.0 |
| 2026-09-26 10:08:08 | POST   | /users   |  409.0 |
| 2026-09-26 10:08:08 | POST   | /users   |  422.0 |
| 2026-09-26 10:08:08 | GET    | /users/1 |  200.0 |
| 2026-09-26 10:08:09 | DELETE | /users/2 |  204.0 |
| 2026-09-26 10:08:09 | GET    | /users/2 |  404.0 |
+---------------------+--------+----------+--------+
```

The prices are in euro cents by hour of day, in Paris time:

```bash
❯ bq query --use_legacy_sql=false 'SELECT * FROM api_billing.prices ORDER BY start_hour'
+------------+----------+-------------+
| start_hour | end_hour | price_cents |
+------------+----------+-------------+
|          0 |        8 |           1 |
|          8 |       20 |           5 |
|         20 |       24 |           2 |
+------------+----------+-------------+
```

To compute the bill, I join the logs to the prices. Only successful POSTs are billed:

```bash
❯ bq query --use_legacy_sql=false "SELECT
  COUNT(*) AS billable_calls,
  SUM(p.price_cents) / 100 AS total_eur
FROM api_billing.stdout c
JOIN api_billing.prices p
  ON EXTRACT(HOUR FROM c.timestamp AT TIME ZONE 'Europe/Paris') >= p.start_hour
  AND EXTRACT(HOUR FROM c.timestamp AT TIME ZONE 'Europe/Paris') < p.end_hour
WHERE c.jsonPayload.method = 'POST'
  AND c.jsonPayload.status BETWEEN 200 AND 299"
+----------------+-----------+
| billable_calls | total_eur |
+----------------+-----------+
|              2 |       0.1 |
+----------------+-----------+
```

The two 201 POSTs were made at 12:08 Paris time, in the 8h-20h band, so each costs 5 cents. The 409 and the 422 are not billed.

Note on security: the sink writes as its own service account, which only has `bigquery.dataEditor` on the `api_billing` dataset. The app itself has no access to BigQuery.

Note on the first logs: calls made in the first minute after `terraform apply` don't reach BigQuery, because the sink starts writing only once its IAM grant has propagated. They are still in Cloud Logging (30-day retention). This only happens when the sink is first created, which in production happens once, before any traffic.

### Q6 - Letting an AWS service query BigQuery

I don't have the billing team's AWS, so I opened a free-tier AWS account and played their side with a small stack in [tests/aws-wif/](tests/aws-wif/). It creates two roles with no permissions: `billing-orchestrator`, the one we trust, and `other-role`, which must be refused.

```bash
❯ cd tests/aws-wif && terraform apply
❯ terraform output
aws_account_id = "<aws-account-id>"
aws_role_name = "billing-orchestrator"
billing_role_arn = "arn:aws:iam::<aws-account-id>:role/billing-orchestrator"
other_role_arn = "arn:aws:iam::<aws-account-id>:role/other-role"
```

I copied the account and the role name into `infra/terraform.tfvars` and ran `make apply`:

```hcl
aws_account_id = "<aws-account-id>"
aws_role_name  = "billing-orchestrator"
```

Then I generated the credential file the AWS service would use. It holds no secret, only which pool, provider and service account to use:

```bash
❯ gcloud iam workload-identity-pools create-cred-config \
    projects/468083834460/locations/global/workloadIdentityPools/aws-billing/providers/aws-billing-account \
    --service-account=aws-billing@dataops-case-study-509018.iam.gserviceaccount.com \
    --aws --output-file=aws-billing-cred.json
Created credential configuration file [aws-billing-cred.json].
```

To act as the role from my laptop, `assume.sh` assumes (impersonates) it and exports its temporary credentials, which is where Google's auth library looks for them. I also used a throwaway gcloud config so my own login stays untouched:

```bash
❯ source assume.sh arn:aws:iam::<aws-account-id>:role/billing-orchestrator
arn:aws:sts::<aws-account-id>:assumed-role/billing-orchestrator/wif-test

❯ export CLOUDSDK_CONFIG=$(mktemp -d)
❯ gcloud auth login --cred-file=aws-billing-cred.json
Authenticated with external account credentials for: [aws-billing@dataops-case-study-509018.iam.gserviceaccount.com].
```

After a `GET /` and a `POST /users` on the API, the billing role can read the prices and run the billing query:

```bash
❯ bq query --use_legacy_sql=false 'SELECT * FROM api_billing.prices ORDER BY start_hour'
+------------+----------+-------------+
| start_hour | end_hour | price_cents |
+------------+----------+-------------+
|          0 |        8 |           1 |
|          8 |       20 |           5 |
|         20 |       24 |           2 |
+------------+----------+-------------+

❯ bq query --use_legacy_sql=false "SELECT c.jsonPayload.method, c.jsonPayload.path, c.jsonPayload.status, p.price_cents
FROM api_billing.stdout c
LEFT JOIN api_billing.prices p
  ON EXTRACT(HOUR FROM c.timestamp AT TIME ZONE 'Europe/Paris') >= p.start_hour
  AND EXTRACT(HOUR FROM c.timestamp AT TIME ZONE 'Europe/Paris') < p.end_hour
ORDER BY c.timestamp DESC"
+--------+--------+--------+-------------+
| method |  path  | status | price_cents |
+--------+--------+--------+-------------+
| POST   | /users |  201.0 |           5 |
| GET    | /      |  200.0 |           5 |
+--------+--------+--------+-------------+
```

But it can't write anything:

```bash
❯ bq query --use_legacy_sql=false 'CREATE TABLE api_billing.x AS SELECT 1 AS a'
Access Denied: Dataset dataops-case-study-509018:api_billing: Permission bigquery.tables.create denied on dataset dataops-case-study-509018:api_billing (or it may not exist).
```

Then I switched to `other-role`, same account and same credential file. Google refuses it before it even reaches BigQuery:

```bash
❯ unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_SESSION_TOKEN
❯ source assume.sh arn:aws:iam::<aws-account-id>:role/other-role
arn:aws:sts::<aws-account-id>:assumed-role/other-role/wif-test

❯ gcloud auth print-access-token
ERROR: (gcloud.auth.print-access-token) ('Error code unauthorized_client: The given credential is rejected by the attribute condition.', ...)
```

Note: I had to `unset` first, otherwise the shell is still the billing role, which isn't allowed to assume `other-role`. Also, `bq` only says "no active account" when the exchange fails, `gcloud auth print-access-token` shows the real error.

Finally, the queries show up in the audit logs as the service account, with the AWS role behind it:

```bash
❯ gcloud logging read 'protoPayload.serviceName="bigquery.googleapis.com" AND protoPayload.authenticationInfo.principalEmail="aws-billing@dataops-case-study-509018.iam.gserviceaccount.com"' \
    --freshness=1h --limit=1 --format='yaml(protoPayload.methodName,protoPayload.authenticationInfo)'
protoPayload:
  authenticationInfo:
    principalEmail: aws-billing@dataops-case-study-509018.iam.gserviceaccount.com
    serviceAccountDelegationInfo:
    - principalSubject: principal://iam.googleapis.com/projects/468083834460/locations/global/workloadIdentityPools/aws-billing/subject/arn:aws:sts::<aws-account-id>:assumed-role/billing-orchestrator/wif-test
  methodName: jobservice.getqueryresults
```

Note: my test roles trust my own IAM user so I can assume them from a laptop. The real role would obviously come from some EC2, Lambda or something and AWS would hand it the credentials directly, you would still need the creds JSON inside GOOGLE_APPLICATION_CREDENTIALS to make it work though. The GCP side doesn't change: it only checks the role, not who assumed it.

### Q7 - Improvements and high level requirements

I went back over the high level requirements with everything built so far and looked for what could be better. I built the free changes; the ones that cost money or were too much for this project are listed as not implemented.

#### Q1 - High SLA, resilient infrastructure

1. Three replicas, one per zone: a spot reclaim or a zone loss still leaves 2 pods serving. A PodDisruptionBudget keeps 2 up during upgrades and drains.

Not implemented, but what I would do in production:

1. Regional cluster: today the control plane is in a single zone, with Cloud SQL. A regional one survives a zone loss (~73 USD/month, the free tier only covers a zonal one).

   How: `location = var.region` on `google_container_cluster`.

2. Cloud SQL HA: a standby in another zone with automatic failover. About twice the price, and on a dedicated-core tier since shared-core has no SLA.

   How: `availability_type = "REGIONAL"` and `tier = "db-custom-1-3840"` on `google_sql_database_instance`.

3. On-demand nodes (non spot): spot can reclaim all the nodes at once. An on-demand pool as the base and a spot one for the extra capacity (~+14 EUR/month for 3 nodes).

   How: a second `google_container_node_pool` without `spot = true`.

4. Autoscaling: a HorizontalPodAutoscaler and the cluster autoscaler instead of fixed replicas and nodes, plus a descheduler to rebalance the pods after a reclaim.

   How: `kubernetes_horizontal_pod_autoscaler_v2`, an `autoscaling {}` block on the node pool, and the descheduler Helm chart with `RemovePodsViolatingTopologySpreadConstraint`.

5. Monitoring and alerting: a log-based metric on the 5xx (the Q5 logs already have the status), an alert policy and latency SLOs. A high SLA also means knowing when we break it.

   How: `google_logging_metric` on `jsonPayload.status>=500`, `google_monitoring_alert_policy` with a notification channel, and `google_monitoring_slo`.

#### Q2 - Very little traffic, as cheap as possible

1. A daily cap on BigQuery queries: BQ bills per scanned data, so a bad query can get expensive very fast. The project quota is now 10 GiB/day, which stays in the free 1 TiB/month.

2. No public IPs on the nodes (see Q3): it also removes 3 billed IPs, ~19 EUR/month.

Not implemented, but what I would do in production:

1. Budget alert: I set one up in the console, in production it would be in Terraform.

2. GKE Autopilot: billed per pod request instead of per node, its fee is covered by the free tier too, and the control plane is regional (Q1).

   How: `enable_autopilot = true` on `google_container_cluster`, and remove the node pool.

3. Cost labels: know which team or service costs what, from the billing export in BigQuery.

   How: `default_labels` in the `google` provider block, and the billing export turned on in the console.

#### Q3 - Expose the API to a given network, as securely as possible

1. Nodes without public IPs: nobody should reach the nodes, only the load balancer. They still pull the image and send logs through Private Google Access.

2. A dedicated service account for the nodes: they were running as the default Compute Engine one, which has Editor on the whole project. Now they can only write logs and metrics and pull our images.

3. The app runs as non-root: the container didn't need root, so a compromised app can do less.

Not implemented, but what I would do in production:

1. HTTPS + API keys: today the traffic is plain HTTP and the IP is the only check. A Google-managed certificate on an HTTPS load balancer, and one API key per customer, only its SHA-256 hash stored. This would break the IP whitelist, so we would need an alternative implementation.

   How: GKE Gateway with `google_certificate_manager_certificate`, one `google_secret_manager_secret` per customer, and a FastAPI dependency checking the `X-API-Key` header.

2. Image supply chain: immutable tags (the git sha) instead of `:latest`, vulnerability scanning, and only images built by the CI can run (assuming prod would have a CI).

   How: `containerscanning.googleapis.com` enabled, and `binary_authorization { evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE" }` on the cluster.

#### Q4 - Small database for sensitive data, cost effective

1. Point in time recovery: we can now restore the DB to any second before a mistake, not only to the last daily backup.

2. UUIDs instead of incremental ids: with `/users/1`, `/users/2`, anyone who reaches the API could list all the users one by one.

Not implemented, but what I would do in production:

1. Deletion protection: this is a case-study project, but in prod we would have `deletion_protection`.

   How: `deletion_protection = true` on `google_sql_database_instance`.

2. A migrator without `cloudsqlsuperuser`: the migration job only needs to create the table, not to be an admin of the whole instance.

   How: `database_roles = []` on the migrator user, and a schema it owns created once by an admin.

3. Audit logs on the data: know who read or changed which rows, not only who connected.

   How: `cloudsql.enable_pgaudit = on` and `pgaudit.log = read,write` in `database_flags`.

#### Q5 - Bill the POST calls by time of day

1. Price versioning: in Q5 the prices had no dates, so changing a price would have changed the bill for all the past calls too. Each price now has a `valid_from` and a `valid_to`.

Not implemented, but what I would do in production:

1. Keep the billing logs on a destroy: today `terraform destroy` deletes the dataset with everything in it.

2. Bill per customer: for this moment we don't have the need for it since there is a single IP and no account.

#### Q6 - Let the AWS billing service query BigQuery, securely

1. The billing team only sees what they need: in Q6 the AWS role could read the raw logs, with pod names, labels and paths holding user ids. Now it reads a separate `billing_shared` dataset with views on only the billing columns.

2. The daily BigQuery cap (Q2) also limits what the AWS service can spend.

Not implemented, but what I would do in production:

1. A quota per caller, so AWS can't use up the whole project's quota on its own.
