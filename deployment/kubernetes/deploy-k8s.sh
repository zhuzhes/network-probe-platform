#!/bin/bash

# Kubernetes deployment script for network probe platform
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}[K8S]${NC} $1"
}

# Default values
NAMESPACE="network-probe"
ACTION="deploy"
SKIP_BUILD=false
REGISTRY=""
TAG="latest"
CONTEXT=""

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -a, --action ACTION      Action to perform (deploy|delete|status) [default: deploy]"
    echo "  -n, --namespace NS       Kubernetes namespace [default: network-probe]"
    echo "  -r, --registry REGISTRY  Docker registry prefix"
    echo "  -t, --tag TAG           Image tag [default: latest]"
    echo "  -c, --context CONTEXT   Kubernetes context to use"
    echo "  --skip-build            Skip building Docker images"
    echo "  -h, --help              Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                      Deploy to default namespace"
    echo "  $0 -a delete            Delete all resources"
    echo "  $0 -r myregistry.com/ -t v1.0.0  Deploy with custom registry and tag"
    echo "  $0 -c prod-cluster      Deploy to specific cluster context"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--action)
            ACTION="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -t|--tag)
            TAG="$2"
            shift 2
            ;;
        -c|--context)
            CONTEXT="$2"
            shift 2
            ;;
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# Validate action
if [[ "$ACTION" != "deploy" && "$ACTION" != "delete" && "$ACTION" != "status" ]]; then
    print_error "Action must be one of: deploy, delete, status"
    exit 1
fi

# Set kubectl context if specified
if [[ -n "$CONTEXT" ]]; then
    print_status "Switching to Kubernetes context: $CONTEXT"
    kubectl config use-context "$CONTEXT"
fi

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl is not installed or not in PATH"
    exit 1
fi

# Check cluster connectivity
if ! kubectl cluster-info &> /dev/null; then
    print_error "Cannot connect to Kubernetes cluster"
    exit 1
fi

print_header "Network Probe Platform Kubernetes Deployment"
print_status "Action: $ACTION"
print_status "Namespace: $NAMESPACE"
print_status "Registry: ${REGISTRY:-"(none)"}"
print_status "Tag: $TAG"

case $ACTION in
    "deploy")
        # Build images if not skipped
        if [[ "$SKIP_BUILD" != true ]]; then
            print_status "Building Docker images..."
            cd ..
            ./build-images.sh -c all -r "$REGISTRY" -t "$TAG"
            if [[ -n "$REGISTRY" ]]; then
                ./build-images.sh -c all -r "$REGISTRY" -t "$TAG" -p
            fi
            cd kubernetes
        fi

        # Create namespace
        print_status "Creating namespace..."
        kubectl apply -f namespace.yaml

        # Apply configurations
        print_status "Applying ConfigMaps and Secrets..."
        kubectl apply -f configmap.yaml
        kubectl apply -f secrets.yaml

        # Apply PVCs
        print_status "Creating Persistent Volume Claims..."
        kubectl apply -f pvc.yaml

        # Deploy data services
        print_status "Deploying PostgreSQL..."
        kubectl apply -f postgres.yaml

        print_status "Deploying Redis..."
        kubectl apply -f redis.yaml

        print_status "Deploying RabbitMQ..."
        kubectl apply -f rabbitmq.yaml

        # Wait for data services to be ready
        print_status "Waiting for data services to be ready..."
        kubectl wait --for=condition=available --timeout=300s deployment/network-probe-postgres -n "$NAMESPACE"
        kubectl wait --for=condition=available --timeout=300s deployment/network-probe-redis -n "$NAMESPACE"
        kubectl wait --for=condition=available --timeout=300s deployment/network-probe-rabbitmq -n "$NAMESPACE"

        # Update management deployment with correct image
        if [[ -n "$REGISTRY" ]]; then
            sed -i.bak "s|image: network-probe-management:latest|image: ${REGISTRY}network-probe-management:${TAG}|g" management.yaml
        fi

        # Deploy management platform
        print_status "Deploying Management Platform..."
        kubectl apply -f management.yaml

        # Wait for management platform to be ready
        print_status "Waiting for Management Platform to be ready..."
        kubectl wait --for=condition=available --timeout=300s deployment/network-probe-management -n "$NAMESPACE"

        # Deploy ingress
        print_status "Deploying Ingress..."
        kubectl apply -f ingress.yaml

        print_header "Deployment completed successfully!"
        print_status "Check status with: kubectl get all -n $NAMESPACE"
        ;;

    "delete")
        print_warning "This will delete all resources in namespace $NAMESPACE"
        read -p "Are you sure? (y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            print_status "Deleting all resources..."
            kubectl delete namespace "$NAMESPACE" --ignore-not-found=true
            print_status "All resources deleted"
        else
            print_status "Deletion cancelled"
        fi
        ;;

    "status")
        print_status "Checking deployment status..."
        echo
        print_header "Namespace:"
        kubectl get namespace "$NAMESPACE" 2>/dev/null || echo "Namespace not found"
        echo
        print_header "Deployments:"
        kubectl get deployments -n "$NAMESPACE" 2>/dev/null || echo "No deployments found"
        echo
        print_header "Services:"
        kubectl get services -n "$NAMESPACE" 2>/dev/null || echo "No services found"
        echo
        print_header "Ingress:"
        kubectl get ingress -n "$NAMESPACE" 2>/dev/null || echo "No ingress found"
        echo
        print_header "Pods:"
        kubectl get pods -n "$NAMESPACE" 2>/dev/null || echo "No pods found"
        echo
        print_header "PVCs:"
        kubectl get pvc -n "$NAMESPACE" 2>/dev/null || echo "No PVCs found"
        ;;
esac