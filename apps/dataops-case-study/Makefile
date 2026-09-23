PROJECT_ID ?= dataops-case-study-509018
REGION     ?= europe-west1
REGISTRY   := $(REGION)-docker.pkg.dev
IMAGE      := $(REGISTRY)/$(PROJECT_ID)/dataops/fast-api-hello:latest

.PHONY: push

# Build the FastAPI image for the GKE nodes (amd64, not the local arm64) and push it to Artifact Registry
push:
	gcloud auth configure-docker $(REGISTRY) --quiet
	docker build --platform linux/amd64 -t $(IMAGE) apps/fast-api-hello
	docker push $(IMAGE)
