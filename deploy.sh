#!/bin/bash

# Celluloid Video Analysis API Deployment Script

set -e

echo "🚀 Deploying Celluloid Video Analysis API..."

# Build the Docker image
echo "🔨 Building Docker image..."
docker build -t celluloid-video-analysis-api .

# Stop existing container if running
echo "🛑 Stopping existing container..."
docker stop celluloid-video-analysis-api 2>/dev/null || true
docker rm celluloid-video-analysis-api 2>/dev/null || true

# Run one container (api + worker, default: both)
echo "🏃 Starting container (api + worker)..."
docker run -d \
    --name celluloid-video-analysis-api \
    --restart unless-stopped \
    -p 8081:8081 \
    -p 5555:5555 \
    -v "$(pwd)/outputs:/app/outputs" \
    -v "$(pwd)/flower:/app/flower" \
    -v "$(pwd)/models:/app/models" \
    -e REDIS_URL="redis://host.docker.internal:6379/0" \
    -e API_KEY="xxx" \
    -e BASE_URL="http://localhost:8081" \
    -e CELERY_QUEUE_NAME="celluloid_video_processing" \
    -e CELERY_TASK_TIMEOUT="3000" \
    -e FLOWER_UNAUTHENTICATED_API="true" \
    -e FLOWER_PERSISTENT="true" \
    -e FLOWER_DB="/app/flower/flower.db" \
    -e CELLULOID_MODELS_DIR="/app/models" \
    celluloid-video-analysis-api

# Wait for service to be ready
echo "⏳ Waiting for service to be ready..."
for i in {1..30}; do
    if curl -f http://localhost:8081/health > /dev/null 2>&1; then
        echo "✅ Service is ready!"
        break
    fi
    echo "   Waiting... ($i/30)"
    sleep 2
done

# Show container status
echo "📊 Container status:"
docker ps --filter name=celluloid-video-analysis

echo ""
echo "🎉 Deployment complete!"
echo "📡 API is available at: http://localhost:8081"
echo "🔍 Health check at: http://localhost:8081/health"
echo "🔍 Flower is available at: http://localhost:5555"
echo ""
echo "📋 Useful commands:"
echo "   View logs:   docker logs -f celluloid-video-analysis-api"
echo "   Purge queue: docker exec celluloid-video-analysis-api python -m celery -A app.core.celery_app purge -f"
echo "   Stop:       docker stop celluloid-video-analysis-api"
echo "   Restart:    docker restart celluloid-video-analysis-api"
echo "   Remove:     docker rm -f celluloid-video-analysis-api" 