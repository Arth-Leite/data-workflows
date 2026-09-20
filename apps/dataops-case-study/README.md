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
