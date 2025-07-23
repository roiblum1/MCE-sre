import os
import yaml
import aiohttp
import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import re

logger = logging.getLogger(__name__)


class ClusterConfig:
    """Configuration for a single MCE cluster."""
    def __init__(self, name: str, route_url: str, token: Optional[str] = None, 
                 namespace: str = "openshift-mce-monitoring", 
                 service_account: str = "mce-aggregator-reader"):
        self.name = name
        self.route_url = route_url
        self.token = token
        self.namespace = namespace
        self.service_account = service_account
        self.last_success = None
        self.last_failure = None
        self.failure_count = 0


class MultiClusterMetricsAggregator:
    def __init__(self):
        """Initialize the multi-cluster metrics aggregator."""
        self.clusters: Dict[str, ClusterConfig] = {}
        self.aggregated_metrics = ""
        self.cluster_status = {}
        
        # Load Kubernetes config
        try:
            config.load_incluster_config()
            self.in_cluster = True
        except:
            config.load_kube_config()
            self.in_cluster = False
            
        self.core_api = client.CoreV1Api()
        self.custom_api = client.CustomObjectsApi()
        
        # Load cluster configuration
        self._load_cluster_config()
        
        # Create async http session
        self.session = None
        
    def _load_cluster_config(self):
        """Load cluster configuration from ConfigMap or environment."""
        config_file = os.environ.get('CLUSTER_CONFIG_FILE', '/etc/mce-aggregator/clusters.yaml')
        
        # Try to load from file first
        if os.path.exists(config_file):
            logger.info(f"Loading cluster config from {config_file}")
            with open(config_file, 'r') as f:
                config_data = yaml.safe_load(f)
                self._parse_cluster_config(config_data)
        else:
            # Fall back to environment variables
            logger.info("Loading cluster config from environment variables")
            self._load_from_env()
            
    def _parse_cluster_config(self, config_data: dict):
        """Parse cluster configuration from dict."""
        for cluster in config_data.get('clusters', []):
            name = cluster['name']
            
            # Build route URL - support both full URL and just the domain part
            route_url = cluster.get('route_url')
            if not route_url:
                # Build from domain
                domain = cluster.get('domain')
                if domain:
                    route_url = f"https://mce-metrics-exporter-openshift-mce-monitoring.{domain}/metrics"
                else:
                    logger.error(f"No route_url or domain specified for cluster {name}")
                    continue
                    
            self.clusters[name] = ClusterConfig(
                name=name,
                route_url=route_url,
                token=cluster.get('token'),
                namespace=cluster.get('namespace', 'openshift-mce-monitoring'),
                service_account=cluster.get('service_account', 'mce-aggregator-reader')
            )
            logger.info(f"Configured cluster {name} with route {route_url}")
            
    def _load_from_env(self):
        """Load cluster configuration from environment variables."""
        # Format: CLUSTER_1_NAME=cluster1,CLUSTER_1_DOMAIN=apps.cluster1.example.com
        cluster_count = int(os.environ.get('CLUSTER_COUNT', '0'))
        
        for i in range(1, cluster_count + 1):
            name = os.environ.get(f'CLUSTER_{i}_NAME')
            domain = os.environ.get(f'CLUSTER_{i}_DOMAIN')
            token = os.environ.get(f'CLUSTER_{i}_TOKEN')
            
            if name and domain:
                route_url = f"https://mce-metrics-exporter-openshift-mce-monitoring.{domain}/metrics"
                self.clusters[name] = ClusterConfig(
                    name=name,
                    route_url=route_url,
                    token=token
                )
                logger.info(f"Configured cluster {name} from environment")
                
    async def _get_cluster_token(self, cluster: ClusterConfig) -> str:
        """Get authentication token for a cluster."""
        # If token is already provided, use it
        if cluster.token:
            return cluster.token
            
        # Try to get token from service account secret
        try:
            # Look for service account token secret
            secret_name = f"{cluster.service_account}-token"
            secret = self.core_api.read_namespaced_secret(
                name=secret_name,
                namespace=cluster.namespace
            )
            
            token = secret.data.get('token')
            if token:
                import base64
                return base64.b64decode(token).decode('utf-8')
                
        except ApiException as e:
            logger.warning(f"Could not get token from secret for {cluster.name}: {e}")
            
        # If in cluster, try to use current service account token
        if self.in_cluster:
            token_file = '/var/run/secrets/kubernetes.io/serviceaccount/token'
            if os.path.exists(token_file):
                with open(token_file, 'r') as f:
                    return f.read()
                    
        return ""
        
    async def _fetch_cluster_metrics(self, cluster: ClusterConfig) -> Tuple[str, bool]:
        """Fetch metrics from a single cluster."""
        start_time = time.time()
        
        try:
            # Get authentication token
            token = await self._get_cluster_token(cluster)
            
            headers = {}
            if token:
                headers['Authorization'] = f'Bearer {token}'
                
            # Create session if not exists
            if not self.session:
                timeout = aiohttp.ClientTimeout(total=30)
                connector = aiohttp.TCPConnector(ssl=False)  # For self-signed certs
                self.session = aiohttp.ClientSession(
                    timeout=timeout,
                    connector=connector
                )
                
            async with self.session.get(cluster.route_url, headers=headers) as response:
                if response.status == 200:
                    metrics_text = await response.text()
                    
                    # Process metrics to add cluster label
                    processed_metrics = self._add_cluster_label(metrics_text, cluster.name)
                    
                    # Update status
                    cluster.last_success = datetime.now()
                    cluster.failure_count = 0
                    
                    duration = time.time() - start_time
                    logger.info(f"Successfully fetched metrics from {cluster.name} in {duration:.2f}s")
                    
                    return processed_metrics, True
                else:
                    error_msg = f"HTTP {response.status}: {await response.text()}"
                    logger.error(f"Failed to fetch metrics from {cluster.name}: {error_msg}")
                    cluster.last_failure = datetime.now()
                    cluster.failure_count += 1
                    return f"# Error fetching from {cluster.name}: {error_msg}\n", False
                    
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching metrics from {cluster.name}")
            cluster.last_failure = datetime.now()
            cluster.failure_count += 1
            return f"# Error fetching from {cluster.name}: Timeout\n", False
        except Exception as e:
            logger.error(f"Error fetching metrics from {cluster.name}: {e}")
            cluster.last_failure = datetime.now()
            cluster.failure_count += 1
            return f"# Error fetching from {cluster.name}: {str(e)}\n", False
            
    def _add_cluster_label(self, metrics_text: str, cluster_name: str) -> str:
        """Add source_cluster label to all metrics."""
        lines = metrics_text.split('\n')
        processed_lines = []
        
        for line in lines:
            # Skip empty lines and comments
            if not line or line.startswith('#'):
                processed_lines.append(line)
                continue
                
            # Parse metric line
            match = re.match(r'^([a-zA-Z_:][a-zA-Z0-9_:]*)\s*({[^}]*})?\s*(.+)$', line)
            if match:
                metric_name = match.group(1)
                labels = match.group(2) or '{}'
                value = match.group(3)
                
                # Add source_cluster label
                if labels == '{}':
                    new_labels = f'{{source_cluster="{cluster_name}"}}'
                else:
                    # Insert source_cluster at the beginning of labels
                    new_labels = labels[:-1] + f',source_cluster="{cluster_name}"}}'
                    new_labels = new_labels.replace('{,', '{')  # Fix if labels was empty
                    
                processed_lines.append(f"{metric_name}{new_labels} {value}")
            else:
                processed_lines.append(line)
                
        return '\n'.join(processed_lines)
        
    async def aggregate_all_metrics(self):
        """Aggregate metrics from all configured clusters."""
        logger.info(f"Starting aggregation for {len(self.clusters)} clusters")
        
        # Fetch metrics from all clusters concurrently
        tasks = []
        for cluster_name, cluster_config in self.clusters.items():
            task = self._fetch_cluster_metrics(cluster_config)
            tasks.append((cluster_name, task))
            
        # Wait for all fetches to complete
        results = []
        for cluster_name, task in tasks:
            metrics, success = await task
            results.append((cluster_name, metrics, success))
            self.cluster_status[cluster_name] = {
                'success': success,
                'last_attempt': datetime.now().isoformat(),
                'failure_count': self.clusters[cluster_name].failure_count
            }
            
        # Combine all metrics
        combined_metrics = []
        
        # Add aggregator metadata
        combined_metrics.append("# HELP mce_aggregator_info Multi-cluster MCE metrics aggregator info")
        combined_metrics.append("# TYPE mce_aggregator_info gauge")
        combined_metrics.append(f'mce_aggregator_info{{version="2.0.0",clusters="{len(self.clusters)}"}} 1')
        combined_metrics.append("")
        
        # Add cluster status metrics
        combined_metrics.append("# HELP mce_aggregator_cluster_up Whether the cluster metrics are being collected successfully")
        combined_metrics.append("# TYPE mce_aggregator_cluster_up gauge")
        for cluster_name, (_, _, success) in zip(self.clusters.keys(), results):
            status = 1 if success else 0
            combined_metrics.append(f'mce_aggregator_cluster_up{{cluster="{cluster_name}"}} {status}')
        combined_metrics.append("")
        
        # Add all cluster metrics
        for cluster_name, metrics, success in results:
            if success and metrics:
                combined_metrics.append(f"# Metrics from cluster: {cluster_name}")
                combined_metrics.append(metrics)
                combined_metrics.append("")
                
        self.aggregated_metrics = '\n'.join(combined_metrics)
        logger.info("Aggregation completed")
        
    def get_aggregated_metrics(self) -> str:
        """Get the latest aggregated metrics."""
        return self.aggregated_metrics
        
    def get_cluster_status(self) -> dict:
        """Get status of all monitored clusters."""
        status = {
            'clusters': {},
            'summary': {
                'total': len(self.clusters),
                'up': sum(1 for s in self.cluster_status.values() if s.get('success', False)),
                'down': sum(1 for s in self.cluster_status.values() if not s.get('success', False))
            }
        }
        
        for cluster_name, cluster_config in self.clusters.items():
            status['clusters'][cluster_name] = {
                'route_url': cluster_config.route_url,
                'status': self.cluster_status.get(cluster_name, {}),
                'last_success': cluster_config.last_success.isoformat() if cluster_config.last_success else None,
                'last_failure': cluster_config.last_failure.isoformat() if cluster_config.last_failure else None
            }
            
        return status
        
    async def close(self):
        """Close any open connections."""
        if self.session:
            await self.session.close()