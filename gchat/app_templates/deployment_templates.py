"""
Deployment Templates for Google Chat Apps

Generates deployment configurations and scripts.
"""

from typing_extensions import Any, Dict

from config.enhanced_logging import setup_logger

logger = setup_logger()


class DeploymentTemplateGenerator:
    """Generates deployment templates for Google Chat apps."""

    def __init__(self):
        self.logger = logger

    def generate_cloud_run_config(
        self, app_name: str, project_id: str
    ) -> Dict[str, Any]:
        """Generate Google Cloud Run deployment configuration."""

        safe_name = app_name.lower().replace(" ", "-").replace("_", "-")

        return {
            "dockerfile": f"""FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8080

CMD ["python", "webhook_{safe_name.replace('-', '_')}.py"]
""",
            "cloudbuild_yaml": f"""steps:
  - name: 'gcr.io/cloud-builders/docker'
    args: ['build', '-t', 'gcr.io/{project_id}/{safe_name}', '.']
  - name: 'gcr.io/cloud-builders/docker'
    args: ['push', 'gcr.io/{project_id}/{safe_name}']
  - name: 'gcr.io/cloud-builders/gcloud'
    args:
      - 'run'
      - 'deploy'
      - '{safe_name}'
      - '--image'
      - 'gcr.io/{project_id}/{safe_name}'
      - '--platform'
      - 'managed'
      - '--region'
      - 'us-central1'
      - '--allow-unauthenticated'
      - '--port'
      - '8080'
images:
  - 'gcr.io/{project_id}/{safe_name}'
""",
            "requirements_txt": """fastapi==0.115.14
uvicorn==0.32.1
google-auth==2.23.3
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
google-api-python-client==2.103.0
requests==2.31.0
""",
            "deploy_script": f"""#!/bin/bash
# Google Cloud Run Deployment Script
# Generated for: {app_name}

set -e

PROJECT_ID="{project_id}"
SERVICE_NAME="{safe_name}"
REGION="us-central1"

echo "🚀 Deploying {app_name} to Google Cloud Run..."

# Build and deploy
echo "📦 Building and deploying..."
gcloud builds submit --config cloudbuild.yaml

echo "✅ Deployment complete!"
echo "🌐 Service URL: https://${{SERVICE_NAME}}-${{REGION}}-${{PROJECT_ID}}.a.run.app"
echo "📋 Webhook URL: https://${{SERVICE_NAME}}-${{REGION}}-${{PROJECT_ID}}.a.run.app/webhook"
""",
            "app_yaml": """runtime: python39

env_variables:
  FASTAPI_ENV: production

automatic_scaling:
  min_instances: 0
  max_instances: 10

handlers:
- url: /webhook
  script: auto
  secure: always

- url: /.*
  script: auto
  secure: always
""",
        }

    def generate_app_engine_config(self, app_name: str) -> Dict[str, Any]:
        """Generate Google App Engine deployment configuration."""

        safe_name = app_name.lower().replace(" ", "_")

        return {
            "app_yaml": """runtime: python39

env_variables:
  FASTAPI_ENV: production

automatic_scaling:
  min_instances: 0
  max_instances: 10

handlers:
- url: /webhook
  script: auto
  secure: always

- url: /.*
  script: auto
  secure: always
""",
            "requirements_txt": """fastapi==0.115.14
uvicorn==0.32.1
google-auth==2.23.3
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
google-api-python-client==2.103.0
requests==2.31.0
""",
            "deploy_script": f"""#!/bin/bash
# Google App Engine Deployment Script
# Generated for: {app_name}

set -e

echo "🚀 Deploying {app_name} to Google App Engine..."

# Deploy to App Engine
echo "📦 Deploying..."
gcloud app deploy app.yaml --quiet

echo "✅ Deployment complete!"
echo "🌐 App URL: $(gcloud app describe --format='value(defaultHostname)')"
echo "📋 Webhook URL: https://$(gcloud app describe --format='value(defaultHostname)')/webhook"
""",
            "main_py": f"""# App Engine requires main.py as entry point
from webhook_{safe_name} import app
import uvicorn

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8080)
""",
        }

    def generate_docker_config(self, app_name: str) -> Dict[str, Any]:
        """Generate Docker deployment configuration."""

        safe_name = app_name.lower().replace(" ", "_")

        return {
            "dockerfile": f"""FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \\
  CMD curl -f http://localhost:8080/webhook || exit 1

# Run the application
CMD ["python", "webhook_{safe_name}.py"]
""",
            "docker_compose_yaml": f"""version: '3.8'

services:
  {safe_name}:
    build: .
    ports:
      - "8080:8080"
    environment:
      - FASTAPI_ENV=production
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/webhook"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 30s
""",
            "requirements_txt": """fastapi==0.115.14
uvicorn==0.32.1
google-auth==2.23.3
google-auth-oauthlib==1.1.0
google-auth-httplib2==0.1.1
google-api-python-client==2.103.0
requests==2.31.0
""",
            "deploy_script": f"""#!/bin/bash
# Docker Deployment Script
# Generated for: {app_name}

set -e

echo "🚀 Deploying {app_name} with Docker..."

# Build the image
echo "📦 Building Docker image..."
docker build -t {safe_name} .

# Run the container
echo "🌐 Starting container..."
docker run -d \\
  --name {safe_name} \\
  -p 8080:8080 \\
  --restart unless-stopped \\
  {safe_name}

echo "✅ Deployment complete!"
echo "🌐 App URL: http://localhost:8080"
echo "📋 Webhook URL: http://localhost:8080/webhook"
echo "🔍 Container logs: docker logs {safe_name}"
""",
        }

    def generate_kubernetes_config(
        self, app_name: str, project_id: str
    ) -> Dict[str, Any]:
        """Generate Kubernetes deployment configuration."""

        safe_name = app_name.lower().replace(" ", "-").replace("_", "-")

        return {
            "deployment_yaml": f"""apiVersion: apps/v1
kind: Deployment
metadata:
  name: {safe_name}
  labels:
    app: {safe_name}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {safe_name}
  template:
    metadata:
      labels:
        app: {safe_name}
    spec:
      containers:
      - name: {safe_name}
        image: gcr.io/{project_id}/{safe_name}:latest
        ports:
        - containerPort: 8080
        env:
        - name: FASTAPI_ENV
          value: "production"
        resources:
          requests:
            memory: "128Mi"
            cpu: "100m"
          limits:
            memory: "256Mi"
            cpu: "200m"
        livenessProbe:
          httpGet:
            path: /webhook
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /webhook
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: {safe_name}-service
spec:
  selector:
    app: {safe_name}
  ports:
    - protocol: TCP
      port: 80
      targetPort: 8080
  type: LoadBalancer
""",
            "ingress_yaml": f"""apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {safe_name}-ingress
  annotations:
    kubernetes.io/ingress.global-static-ip-name: {safe_name}-ip
    networking.gke.io/managed-certificates: {safe_name}-ssl-cert
spec:
  rules:
  - host: {safe_name}.example.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: {safe_name}-service
            port:
              number: 80
---
apiVersion: networking.gke.io/v1
kind: ManagedCertificate
metadata:
  name: {safe_name}-ssl-cert
spec:
  domains:
    - {safe_name}.example.com
""",
            "deploy_script": f"""#!/bin/bash
# Kubernetes Deployment Script
# Generated for: {app_name}

set -e

echo "🚀 Deploying {app_name} to Kubernetes..."

# Build and push image
echo "📦 Building and pushing image..."
docker build -t gcr.io/{project_id}/{safe_name}:latest .
docker push gcr.io/{project_id}/{safe_name}:latest

# Apply Kubernetes configurations
echo "⚙️ Applying Kubernetes configurations..."
kubectl apply -f deployment.yaml
kubectl apply -f ingress.yaml

# Wait for deployment
echo "⏳ Waiting for deployment to be ready..."
kubectl rollout status deployment/{safe_name}

echo "✅ Deployment complete!"
echo "🌐 Service: kubectl get service {safe_name}-service"
echo "🔍 Pods: kubectl get pods -l app={safe_name}"
""",
        }

    def list_deployment_options(self) -> Dict[str, Any]:
        """List all available deployment options."""
        return {
            "cloud_run": {
                "description": "Google Cloud Run - Serverless, fully managed",
                "benefits": [
                    "Auto-scaling",
                    "Pay-per-use",
                    "HTTPS included",
                    "Easy deployment",
                ],
                "best_for": "Most Chat apps, development, and production",
            },
            "app_engine": {
                "description": "Google App Engine - Platform as a Service",
                "benefits": [
                    "Automatic scaling",
                    "Built-in services",
                    "Version management",
                ],
                "best_for": "Apps needing Google Cloud services integration",
            },
            "docker": {
                "description": "Docker containers - Portable deployment",
                "benefits": [
                    "Consistent environments",
                    "Easy local development",
                    "Portable",
                ],
                "best_for": "Local development, hybrid cloud, custom infrastructure",
            },
            "kubernetes": {
                "description": "Kubernetes - Container orchestration",
                "benefits": ["High availability", "Advanced scaling", "Service mesh"],
                "best_for": "Large-scale applications, microservices architecture",
            },
        }
