PROJECT_ID ?= dataops-case-study-509018
REGION     ?= europe-west1
REGISTRY   := $(REGION)-docker.pkg.dev
IMAGE      := $(REGISTRY)/$(PROJECT_ID)/dataops/fast-api-hello:latest
MY_IP_VAR  := -var="my_ip=$$(curl -fsS https://checkip.amazonaws.com)/32"

.PHONY: push apply destroy

# Build the FastAPI image for the GKE nodes (amd64, not the local arm64) and push it to Artifact Registry
push:
	gcloud auth configure-docker $(REGISTRY) --quiet
	docker build --platform linux/amd64 -t $(IMAGE) apps/fast-api-hello
	docker push $(IMAGE)

apply:
	caffeinate -i terraform -chdir=infra apply $(MY_IP_VAR)

destroy:
	caffeinate -i terraform -chdir=infra destroy $(MY_IP_VAR)
