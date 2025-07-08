import os
import asyncio
import logging
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import PlainTextResponse
import uvicorn
from collector import OpenShiftMetricsCollector
from prometheus_exporter import PrometheusMetricsExporter

# Configure logging
logging.basicConfig(
    level=os.environ.get('LOG_LEVEL', 'INFO'),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global exporter instance
exporter = None
collection_task = None


async def collect_metrics_periodically(interval: int):
    """Background task to collect metrics periodically."""
    while True:
        try:
            await asyncio.sleep(interval)
            logger.info("Performing periodic metrics collection...")
            exporter.collect_and_update()
            logger.info("Periodic collection completed")
        except asyncio.CancelledError:
            logger.info("Metrics collection task cancelled")
            break
        except Exception as e:
            logger.error(f"Periodic collection failed: {e}", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global exporter, collection_task
    
    # Startup
    logger.info("Starting OpenShift MCE Metrics Exporter...")
    
    # Configuration from environment variables
    collection_interval = int(os.environ.get('COLLECTION_INTERVAL', '60'))
    in_cluster = os.environ.get('IN_CLUSTER', 'true').lower() == 'true'
    
    logger.info(f"Collection Interval: {collection_interval}s, In Cluster: {in_cluster}")
    
    # Initialize collector and exporter
    try:
        collector = OpenShiftMetricsCollector(in_cluster=in_cluster)
        exporter = PrometheusMetricsExporter(collector)
        
        # Initial collection
        logger.info("Performing initial metrics collection...")
        exporter.collect_and_update()
        logger.info("Initial collection completed successfully")
        
        # Start background collection task
        collection_task = asyncio.create_task(
            collect_metrics_periodically(collection_interval)
        )
        
    except Exception as e:
        logger.error(f"Failed to initialize exporter: {e}", exc_info=True)
        raise
    
    yield
    
    # Shutdown
    logger.info("Shutting down OpenShift MCE Metrics Exporter...")
    if collection_task:
        collection_task.cancel()
        try:
            await collection_task
        except asyncio.CancelledError:
            pass


# Create FastAPI app with lifespan manager
app = FastAPI(
    title="OpenShift MCE Metrics Exporter",
    description="Prometheus exporter for OpenShift MCE infrastructure metrics",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics():
    """Endpoint for Prometheus to scrape metrics."""
    try:
        if exporter:
            return Response(
                content=exporter.generate_metrics(),
                media_type="text/plain; version=0.0.4; charset=utf-8"
            )
        else:
            return Response(
                content="Exporter not initialized",
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
    if exporter:
        return "OK"
    else:
        return Response(content="Not Ready", status_code=503)


@app.get("/ready", response_class=PlainTextResponse)
async def ready():
    """Readiness check endpoint."""
    if exporter:
        return "OK"
    else:
        return Response(content="Not Ready", status_code=503)


@app.get("/")
async def root():
    """Root endpoint with basic info."""
    return {
        "service": "OpenShift MCE Metrics Exporter",
        "endpoints": {
            "/metrics": "Prometheus metrics",
            "/health": "Health check",
            "/ready": "Readiness check"
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