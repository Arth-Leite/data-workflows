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