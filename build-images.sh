#!/bin/bash

# Build script for network probe platform Docker images
set -e

# Default values
REGISTRY=""
TAG="latest"
PUSH=false
COMPONENT=""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
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

# Function to show usage
usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  -c, --component COMPONENT  Build specific component (management|agent|all)"
    echo "  -r, --registry REGISTRY    Docker registry prefix (e.g., myregistry.com/)"
    echo "  -t, --tag TAG             Image tag (default: latest)"
    echo "  -p, --push                Push images to registry after building"
    echo "  -h, --help                Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 -c all                 Build both management and agent images"
    echo "  $0 -c management -t v1.0.0 Build management image with tag v1.0.0"
    echo "  $0 -c agent -r myregistry.com/ -t v1.0.0 -p"
    echo "                            Build agent image, tag with registry prefix and push"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--component)
            COMPONENT="$2"
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
        -p|--push)
            PUSH=true
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

# Validate component
if [[ -z "$COMPONENT" ]]; then
    print_error "Component must be specified"
    usage
    exit 1
fi

if [[ "$COMPONENT" != "management" && "$COMPONENT" != "agent" && "$COMPONENT" != "all" ]]; then
    print_error "Component must be one of: management, agent, all"
    exit 1
fi

# Build function
build_image() {
    local component=$1
    local image_name="${REGISTRY}network-probe-${component}:${TAG}"
    
    print_status "Building ${component} image: ${image_name}"
    
    if [[ "$component" == "management" ]]; then
        docker build --build-arg COMPONENT=management -t "${image_name}" -f Dockerfile .
    elif [[ "$component" == "agent" ]]; then
        docker build --build-arg COMPONENT=agent -t "${image_name}" -f Dockerfile .
    fi
    
    print_status "Successfully built ${image_name}"
    
    if [[ "$PUSH" == true ]]; then
        print_status "Pushing ${image_name} to registry"
        docker push "${image_name}"
        print_status "Successfully pushed ${image_name}"
    fi
}

# Main execution
print_status "Starting Docker image build process"
print_status "Component: ${COMPONENT}"
print_status "Registry: ${REGISTRY:-"(none)"}"
print_status "Tag: ${TAG}"
print_status "Push: ${PUSH}"

if [[ "$COMPONENT" == "all" ]]; then
    build_image "management"
    build_image "agent"
elif [[ "$COMPONENT" == "management" || "$COMPONENT" == "agent" ]]; then
    build_image "$COMPONENT"
fi

print_status "Build process completed successfully!"