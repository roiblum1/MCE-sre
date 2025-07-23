import os
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse
import uvicorn
from multi_cluster_aggregator import MultiClusterMetricsAggregator

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global aggregator instance
aggregator = None
collection_task = None


async def aggregate_metrics_periodically(interval: int):
    """Background task to aggregate metrics from all clusters periodically."""
    while True:
        try:
            await asyncio.sleep(interval)
            logger.info("Performing periodic metrics aggregation...")
            await aggregator.aggregate_all_metrics()
            logger.info("Periodic aggregation completed")
        except asyncio.CancelledError:
            logger.info("Metrics aggregation task cancelled")
            break
        except Exception as e:
            logger.error(f"Periodic aggregation failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global aggregator, collection_task
    
    # Startup
    logger.info("Starting Multi-Cluster MCE Metrics Aggregator...")
    
    # Configuration from environment variables
    collection_interval = int(os.environ.get('COLLECTION_INTERVAL', '60'))
    
    logger.info(f"Collection Interval: {collection_interval}s")
    
    # Initialize aggregator
    try:
        aggregator = MultiClusterMetricsAggregator()
        
        # Initial collection
        logger.info("Performing initial metrics aggregation...")
        await aggregator.aggregate_all_metrics()
        logger.info("Initial aggregation completed successfully")
        
        # Start background collection task
        collection_task = asyncio.create_task(
            aggregate_metrics_periodically(collection_interval)
        )
        
    except Exception as e:
        logger.error(f"Failed to initialize aggregator: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down Multi-Cluster MCE Metrics Aggregator...")
    if collection_task:
        collection_task.cancel()
        try:
            await collection_task
        except asyncio.CancelledError:
            pass


# Create FastAPI app with lifespan manager
app = FastAPI(
    title="Multi-Cluster MCE Metrics Aggregator",
    description="Prometheus aggregator for multiple OpenShift MCE cluster metrics",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Endpoint for Prometheus to scrape aggregated metrics from all clusters."""
    try:
        if aggregator:
            return Response(
                content=aggregator.get_aggregated_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8"
            )
        else:
            return Response(
                content="Aggregator not initialized",
                status_code=500
            )
    except Exception as e:
        logger.error(f"Error generating metrics: {e}", exc_info=True)
        return Response(
            content=f"Error: {str(e)}",
            status_code=500
        )


@app.get("/health", response_class=PlainTextResponse)
async def health():
    """Health check endpoint."""
    if aggregator:
        return "OK"
    else:
        return Response(content="Not Ready", status_code=503)


@app.get("/ready", response_class=PlainTextResponse)
async def ready():
    """Readiness check endpoint."""
    if aggregator:
        return "OK"
    else:
        return Response(content="Not Ready", status_code=503)


@app.get("/clusters")
async def clusters():
    """Get status of all monitored clusters."""
    if aggregator:
        return aggregator.get_cluster_status()
    else:
        return {"error": "Aggregator not initialized"}


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": "Multi-Cluster MCE Metrics Aggregator",
        "endpoints": {
            "/metrics": "Aggregated Prometheus metrics from all clusters",
            "/health": "Health check",
            "/ready": "Readiness check",
            "/clusters": "Status of all monitored clusters"
        }
    }


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Configuration
    port = int(os.environ.get('METRICS_PORT', '8080'))
    host = os.environ.get('METRICS_HOST', '0.0.0.0')
    
    # Run the FastAPI app with uvicorn
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_config={
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                },
            },
            "handlers": {
                "default": {
                    "formatter": "default",
                    "class": "logging.StreamHandler",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": os.environ.get('LOG_LEVEL', 'INFO'),
                "handlers": ["default"],
            },
        }
    )


if __name__ == '__main__':
    main()