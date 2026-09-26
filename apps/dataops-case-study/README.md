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
