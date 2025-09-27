# PDFMathTranslate Docker Deployment

This directory contains Docker deployment configurations for PDFMathTranslate, providing one-click deployment with multiple services including GUI, API, and optional local translation models.

## Quick Start

### Prerequisites
- Docker and Docker Compose installed
- At least 4GB RAM available
- 10GB disk space for images and data

### One-Click Deployment

1. **Clone the repository** (if not already done):
```bash
git clone https://github.com/awwaawwa/PDFMathTranslate-next.git
cd PDFMathTranslate-next
```

2. **Set up environment configuration**:
```bash
# Copy the example environment file
cp .env.example .env

# Edit the .env file to add your API keys (optional)
nano .env
```

3. **Start all services**:
```bash
# Build and start all services
docker-compose up -d

# Or with build if you made changes
docker-compose up -d --build
```

4. **Access the services**:
   - **Web GUI**: http://localhost:7860
   - **API**: http://localhost:8000
   - **API Documentation**: http://localhost:8000/docs
   - **Ollama API**: http://localhost:11434

5. **Check service status**:
```bash
# View logs
docker-compose logs -f

# Check service health
docker-compose ps
```

## Services Overview

### Core Services
- **pdf2zh-gui**: Gradio web interface (port 7860)
- **pdf2zh-api**: FastAPI REST API (port 8000)
- **ollama**: Local LLM service for translation (port 11434)

### Optional Services
- **ollama-webui**: Web interface for Ollama (uncomment in docker-compose.yml)
- **nginx**: Reverse proxy with SSL support (uncomment and configure for production)

## Configuration

### Environment Variables
Edit the `.env` file to configure translation services:

```bash
# Translation APIs (set at least one)
OPENAI_API_KEY=your_openai_key
AZURE_API_KEY=your_azure_key
DEEPL_API_KEY=your_deepl_key
GOOGLE_API_KEY=your_google_key

# Local settings
OLLAMA_HOST=http://ollama:11434
```

### Volume Mounts
The following directories are created automatically:
- `./uploads`: PDF upload directory
- `./outputs`: Translated PDF output directory
- `./cache`: Translation cache directory

### Network Configuration
All services communicate through the `pdf2zh-network` bridge network.

## Usage Examples

### Web GUI
1. Navigate to http://localhost:7860
2. Upload a PDF file
3. Select translation engine
4. Click "Translate"
5. Download the translated PDF

### API Usage
```bash
# Health check
curl http://localhost:8000/health

# Translate PDF (using curl)
curl -X POST "http://localhost:8000/translate" \
  -F "file=@document.pdf" \
  -F "engine=google" \
  -F "target_lang=zh"

# Check translation status
curl http://localhost:8000/status/{task_id}

# Download translated file
curl -O http://localhost:8000/download/{task_id}
```

### Python API Client
```python
import requests
import time

# Upload and translate
files = {'file': open('document.pdf', 'rb')}
data = {'engine': 'google', 'target_lang': 'zh'}
response = requests.post('http://localhost:8000/translate', files=files, data=data)
task_id = response.json()['task_id']

# Wait for completion
while True:
    status = requests.get(f'http://localhost:8000/status/{task_id}').json()
    if status['status'] == 'completed':
        break
    time.sleep(2)

# Download result
requests.get(f'http://localhost:8000/download/{task_id}')
```

## Local Models with Ollama

### Pull Models
```bash
# Pull translation-capable models
docker exec -it pdf2zh-next-ollama-1 ollama pull llama3.2

# Or for Chinese translation
docker exec -it pdf2zh-next-ollama-1 ollama pull qwen2.5
```

### Use in PDF2ZH
Set the Ollama model in the GUI or API:
- **Engine**: `ollama`
- **Model**: `llama3.2` (or your preferred model)

## Production Deployment

### With Nginx Reverse Proxy
1. Uncomment the nginx service in `docker-compose.yml`
2. Configure SSL certificates in `./ssl/`
3. Update `nginx.conf` with your domain
4. Restart services

### SSL Configuration
```bash
# Create SSL directory
mkdir ssl

# Generate self-signed certificate (for testing)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout ssl/key.pem -out ssl/cert.pem

# Or use Let's Encrypt for production
certbot --nginx -d your-domain.com
```

### Environment-Specific Configs
Create environment-specific compose files:
```bash
# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up -d
```

## Monitoring and Maintenance

### Logs
```bash
# View all logs
docker-compose logs -f

# Specific service
docker-compose logs -f pdf2zh-api

# With timestamps
docker-compose logs -t -f
```

### Updates
```bash
# Pull latest images
docker-compose pull

# Rebuild and restart
docker-compose down
docker-compose up -d --build
```

### Cleanup
```bash
# Stop and remove containers
docker-compose down

# Remove volumes (careful - deletes data)
docker-compose down -v

# Remove images
docker image prune -f
```

## Troubleshooting

### Common Issues

1. **Service not starting**: Check logs with `docker-compose logs`
2. **Translation failures**: Verify API keys in `.env` file
3. **Memory issues**: Increase Docker memory limit
4. **Permission errors**: Ensure volume directories exist and are writable

### Performance Tuning

1. **Increase memory**: Edit Docker settings to allocate more RAM
2. **Adjust workers**: Modify `PDF2ZH_THREADS` in `.env`
3. **Enable caching**: Ensure `PDF2ZH_CACHE_ENABLED=true`

### Debug Mode
```bash
# Run with debug output
docker-compose -f docker-compose.yml -f docker-compose.debug.yml up
```

## Security Considerations

1. **API Keys**: Never commit `.env` file with real API keys
2. **Network**: Services are isolated in Docker network
3. **Volumes**: Sensitive data stored in mounted volumes
4. **Rate Limiting**: Nginx configuration includes basic rate limiting
5. **SSL**: Use HTTPS in production with proper certificates

## Backup and Recovery

### Backup Data
```bash
# Backup volumes
tar -czf pdf2zh-backup-$(date +%Y%m%d).tar.gz uploads/ outputs/ cache/

# Backup Ollama models
docker run --rm -v ollama-data:/data -v $(pwd):/backup alpine \
  tar -czf /backup/ollama-models-$(date +%Y%m%d).tar.gz -C /data .
```

### Restore Data
```bash
# Restore volumes
tar -xzf pdf2zh-backup-20240101.tar.gz

# Restore Ollama models
docker run --rm -v ollama-data:/data -v $(pwd):/backup alpine \
  tar -xzf /backup/ollama-models-20240101.tar.gz -C /data
```

## Uninstallation

```bash
# Stop and remove everything
docker-compose down -v

# Remove images
docker rmi pdf2zh-next:latest ollama/ollama:latest

# Remove volumes
docker volume rm pdf2zh-next_ollama-data
```

## Support

For issues and questions:
- Check logs: `docker-compose logs`
- Review documentation: See main README.md
- Report issues: GitHub Issues page