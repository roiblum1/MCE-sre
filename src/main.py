import os
import time
import logging
import signal
import sys
from flask import Flask, Response
from prometheus_client import generate_latest
from collector import OpenShiftMetricsCollector
from prometheus_exporter import PrometheusMetricsExporter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app for metrics endpoint
app = Flask(__name__)

# Global exporter instance
exporter = None


@app.route('/metrics')
def metrics():
    """Endpoint for Prometheus to scrape metrics."""
    try:
        if exporter:
            return Response(exporter.generate_metrics(), mimetype='text/plain')
        else:
            return Response("Exporter not initialized", status=500)
    except Exception as e:
        logger.error(f"Error generating metrics: {e}")
        return Response(f"Error: {str(e)}", status=500)


@app.route('/health')
def health():
    """Health check endpoint."""
    return Response("OK", status=200)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)


def main():
    global exporter
    
    # Register signal handlers
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    # Configuration from environment variables
    port = int(os.environ.get('METRICS_PORT', '8080'))
    collection_interval = int(os.environ.get('COLLECTION_INTERVAL', '60'))
    in_cluster = os.environ.get('IN_CLUSTER', 'true').lower() == 'true'
    
    logger.info(f"Starting OpenShift MCE Metrics Exporter...")
    logger.info(f"Port: {port}, Collection Interval: {collection_interval}s, In Cluster: {in_cluster}")
    
    # Initialize collector and exporter
    collector = OpenShiftMetricsCollector(in_cluster=in_cluster)
    exporter = PrometheusMetricsExporter(collector)
    
    # Initial collection
    try:
        logger.info("Performing initial metrics collection...")
        exporter.collect_and_update()
    except Exception as e:
        logger.error(f"Initial collection failed: {e}")
    
    # Start background collection thread
    import threading
    
    def collect_metrics_periodically():
        while True:
            time.sleep(collection_interval)
            try:
                exporter.collect_and_update()
            except Exception as e:
                logger.error(f"Periodic collection failed: {e}")
    
    collection_thread = threading.Thread(target=collect_metrics_periodically, daemon=True)
    collection_thread.start()
    
    # Start Flask app
    logger.info(f"Starting metrics server on port {port}...")
    app.run(host='0.0.0.0', port=port)


if __name__ == '__main__':
    main()