# Defaults to the project selected in gcloud; override with PROJECT_ID=...
PROJECT_ID ?= $(shell gcloud config get-value project 2>/dev/null)
REGION     ?= europe-west1
REGISTRY   := $(REGION)-docker.pkg.dev
IMAGE      := $(REGISTRY)/$(PROJECT_ID)/images/fast-api-hello:latest
MY_IP_VAR  := -var="my_ip=$$(curl -fsS https://checkip.amazonaws.com)/32"
TF_VARS    := $(MY_IP_VAR) -var="project_id=$(PROJECT_ID)"

.PHONY: push apply refresh destroy

# Build the FastAPI image for the GKE nodes (amd64, not the local arm64) and push it to Artifact Registry
push:
	gcloud auth configure-docker $(REGISTRY) --quiet
	docker build --platform linux/amd64 -t $(IMAGE) apps/fast-api-hello
	docker push $(IMAGE)

apply:
	caffeinate -i terraform -chdir=infra apply $(TF_VARS)
	$(MAKE) refresh

# Point kubectl at the cluster; its endpoint changes whenever the cluster is recreated
refresh:
	gcloud container clusters get-credentials $$(terraform -chdir=infra output -raw cluster_name) \
		--location $$(terraform -chdir=infra output -raw cluster_location) --project $(PROJECT_ID)

destroy:
	caffeinate -i terraform -chdir=infra destroy $(TF_VARS)
