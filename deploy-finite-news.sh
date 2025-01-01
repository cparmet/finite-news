#!/bin/bash

# This script deploys the code to a Cloud Run job, from source. The one command does 3 steps:
# 1. Builds the container
# 2. Uploads it to Artifact Registry
# 3. Deploys the job to Cloud Run

FN_PROJECT_ID=$(gcloud config get project)
FN_REGION=${FN_REGION:=us-east4} # default region if not defined
JOB_NAME=finite-news

# https://cloud.google.com/sdk/gcloud/reference/run/jobs/deploy
gcloud run jobs deploy $JOB_NAME \
    --source . \
    --tasks 1 \
    --max-retries 0 \
    --region $FN_REGION \
    --project=$FN_PROJECT_ID \
    --set-secrets=FN_BUCKET_NAME=FN_BUCKET_NAME:latest,OPENAI_API_KEY=OPENAI_API_KEY:latest,SENDGRID_API_KEY=SENDGRID_API_KEY:latest \
    --memory="1Gi" \
    --task-timeout="45m"
    
