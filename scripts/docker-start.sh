#!/bin/bash

# PDFMathTranslate Docker Quick Start Script
# This script provides a simple interface for deploying PDFMathTranslate with Docker

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
ENVIRONMENT="production"
COMPOSE_FILE="docker-compose.yml"
PULL_IMAGES=false
BUILD_IMAGES=false
VERBOSE=false

# Functions
print_help() {
    echo -e "${BLUE}PDFMathTranslate Docker Quick Start${NC}"
    echo -e ""
    echo -e "${GREEN}Usage:${NC} $0 [OPTIONS]"
    echo -e ""
    echo -e "${GREEN}Options:${NC}"
    echo -e "  -e, --environment ENV    Environment type: dev, prod (default: prod)"
    echo -e "  -p, --pull               Pull latest images before starting"
    echo -e "  -b, --build              Build images before starting"
    echo -e "  -v, --verbose            Verbose output"
    echo -e "  -h, --help               Show this help message"
    echo -e ""
    echo -e "${GREEN}Examples:${NC}"
    echo -e "  $0                       # Start in production mode"
    echo -e "  $0 -e dev                # Start in development mode"
    echo -e "  $0 -p -b                 # Pull and build before starting"
    echo -e "  $0 --build --verbose     # Build with verbose output"
}

log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed. Please install Docker first."
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi

    # Check if Docker daemon is running
    if ! docker info &> /dev/null; then
        log_error "Docker daemon is not running. Please start Docker first."
        exit 1
    fi

    log_success "Dependencies check passed"
}

setup_environment() {
    log_info "Setting up environment..."

    # Create necessary directories
    mkdir -p uploads outputs cache logs

    # Create .env file if it doesn't exist
    if [ ! -f .env ]; then
        log_info "Creating .env file from template..."
        cp .env.example .env
        log_warning "Please edit .env file to add your API keys if needed"
    fi

    # Set proper permissions
    chmod 755 uploads outputs cache logs

    log_success "Environment setup completed"
}

determine_compose_files() {
    case $ENVIRONMENT in
        "dev"|"development")
            COMPOSE_FILE="docker-compose.yml -f docker-compose.dev.yml"
            log_info "Using development configuration"
            ;;
        "prod"|"production")
            COMPOSE_FILE="docker-compose.yml -f docker-compose.prod.yml"
            log_info "Using production configuration"
            ;;
        "base")
            COMPOSE_FILE="docker-compose.yml"
            log_info "Using base configuration"
            ;;
        *)
            log_error "Invalid environment: $ENVIRONMENT"
            exit 1
            ;;
    esac
}

pull_images() {
    if [ "$PULL_IMAGES" = true ]; then
        log_info "Pulling latest images..."
        if [ "$VERBOSE" = true ]; then
            docker-compose $COMPOSE_FILE pull
        else
            docker-compose $COMPOSE_FILE pull > /dev/null 2>&1
        fi
        log_success "Images pulled successfully"
    fi
}

build_images() {
    if [ "$BUILD_IMAGES" = true ]; then
        log_info "Building images..."
        if [ "$VERBOSE" = true ]; then
            docker-compose $COMPOSE_FILE build
        else
            docker-compose $COMPOSE_FILE build > /dev/null 2>&1
        fi
        log_success "Images built successfully"
    fi
}

start_services() {
    log_info "Starting PDFMathTranslate services..."

    if [ "$VERBOSE" = true ]; then
        docker-compose $COMPOSE_FILE up -d
    else
        docker-compose $COMPOSE_FILE up -d > /dev/null 2>&1
    fi

    log_success "Services started successfully"
}

wait_for_services() {
    log_info "Waiting for services to be ready..."

    # Wait for GUI service
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -f http://localhost:7860/ &> /dev/null; then
            log_success "GUI service is ready at http://localhost:7860"
            break
        fi

        attempt=$((attempt + 1))
        sleep 2
    done

    if [ $attempt -eq $max_attempts ]; then
        log_warning "GUI service may not be fully ready yet"
    fi

    # Wait for API service
    attempt=0
    while [ $attempt -lt $max_attempts ]; do
        if curl -f http://localhost:8000/health &> /dev/null; then
            log_success "API service is ready at http://localhost:8000"
            log_success "API documentation at http://localhost:8000/docs"
            break
        fi

        attempt=$((attempt + 1))
        sleep 2
    done

    if [ $attempt -eq $max_attempts ]; then
        log_warning "API service may not be fully ready yet"
    fi
}

show_status() {
    log_info "Service Status:"
    docker-compose $COMPOSE_FILE ps

    echo -e ""
    log_info "Access URLs:"
    case $ENVIRONMENT in
        "dev"|"development")
            echo -e "  ${BLUE}GUI:${NC} http://localhost:7861"
            echo -e "  ${BLUE}API:${NC} http://localhost:8001"
            ;;
        *)
            echo -e "  ${BLUE}GUI:${NC} http://localhost:7860"
            echo -e "  ${BLUE}API:${NC} http://localhost:8000"
            ;;
    esac
    echo -e "  ${BLUE}Ollama:${NC} http://localhost:11434"
    echo -e ""
    log_info "Logs: docker-compose logs -f"
    log_info "Stop: docker-compose down"
}

# Main execution
main() {
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            -e|--environment)
                ENVIRONMENT="$2"
                shift 2
                ;;
            -p|--pull)
                PULL_IMAGES=true
                shift
                ;;
            -b|--build)
                BUILD_IMAGES=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                print_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                print_help
                exit 1
                ;;
        esac
    done

    # Print banner
    echo -e "${BLUE}"
    echo -e "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo -e "║                    PDFMathTranslate Docker Quick Start                       ║"
    echo -e "╚══════════════════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"

    # Execute steps
    check_dependencies
    setup_environment
    determine_compose_files
    pull_images
    build_images
    start_services
    wait_for_services
    show_status

    echo -e ""
    log_success "PDFMathTranslate deployment completed successfully!"
}

# Run main function
main "$@"