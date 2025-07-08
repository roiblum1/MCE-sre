import os
import time
import logging
from prometheus_client import Gauge, Counter, Info, generate_latest, REGISTRY
from prometheus_client.core import CollectorRegistry
from typing import Dict, Any
from models import MetricsData, HostStatus
from collector import OpenShiftMetricsCollector

logger = logging.getLogger(__name__)


class PrometheusMetricsExporter:
    def __init__(self, collector: OpenShiftMetricsCollector):
        self.collector = collector
        self.registry = CollectorRegistry()
        # Get cluster name from environment variable or use default
        self.cluster_name = os.environ.get('CLUSTER_NAME', 'default-cluster')
        self._setup_metrics()
        
    def _setup_metrics(self):
        """Setup Prometheus metrics."""
        # InfraEnv metrics
        self.infraenv_count = Gauge(
            'openshift_mce_infraenv_count',
            'Total number of InfraEnvs',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.infraenv_hosts = Gauge(
            'openshift_mce_infraenv_hosts',
            'Number of hosts in InfraEnv',
            ['cluster_name', 'infraenv_name', 'namespace'],
            registry=self.registry
        )
        
        # NEW: Per-InfraEnv metrics
        self.infraenv_available_hosts = Gauge(
            'openshift_mce_infraenv_available_hosts',
            'Number of available hosts in InfraEnv',
            ['cluster_name', 'infraenv_name', 'namespace'],
            registry=self.registry
        )
        
        self.infraenv_hosts_by_status = Gauge(
            'openshift_mce_infraenv_hosts_by_status',
            'Number of hosts by status in InfraEnv',
            ['cluster_name', 'infraenv_name', 'namespace', 'status'],
            registry=self.registry
        )
        
        self.infraenv_cpu_cores = Gauge(
            'openshift_mce_infraenv_cpu_cores',
            'Total CPU cores in InfraEnv',
            ['cluster_name', 'infraenv_name', 'namespace'],
            registry=self.registry
        )
        
        self.infraenv_memory_gb = Gauge(
            'openshift_mce_infraenv_memory_gb',
            'Total memory in GB in InfraEnv',
            ['cluster_name', 'infraenv_name', 'namespace'],
            registry=self.registry
        )
        
        # Host metrics
        self.host_status = Gauge(
            'openshift_mce_host_status',
            'Host status (1 if in this status, 0 otherwise)',
            ['cluster_name', 'host_id', 'hostname', 'infraenv', 'namespace', 'status'],
            registry=self.registry
        )
        
        self.host_cpu_cores = Gauge(
            'openshift_mce_host_cpu_cores',
            'Number of CPU cores on host',
            ['cluster_name', 'host_id', 'hostname', 'infraenv', 'namespace'],
            registry=self.registry
        )
        
        self.host_memory_mb = Gauge(
            'openshift_mce_host_memory_mb',
            'Memory in MB on host',
            ['cluster_name', 'host_id', 'hostname', 'infraenv', 'namespace'],
            registry=self.registry
        )
        
        self.host_disk_gb = Gauge(
            'openshift_mce_host_disk_gb',
            'Disk space in GB on host',
            ['cluster_name', 'host_id', 'hostname', 'infraenv', 'namespace'],
            registry=self.registry
        )
        
        # Aggregate metrics
        self.total_hosts = Gauge(
            'openshift_mce_total_hosts',
            'Total number of hosts across all InfraEnvs',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.total_available_hosts = Gauge(
            'openshift_mce_total_available_hosts',
            'Total number of available hosts',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.total_hosts_by_status = Gauge(
            'openshift_mce_total_hosts_by_status',
            'Total number of hosts by status',
            ['cluster_name', 'status'],
            registry=self.registry
        )
        
        self.total_cpu_cores = Gauge(
            'openshift_mce_total_cpu_cores',
            'Total CPU cores across all hosts',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.total_memory_gb = Gauge(
            'openshift_mce_total_memory_gb',
            'Total memory in GB across all hosts',
            ['cluster_name'],
            registry=self.registry
        )
        
        # ClusterDeployment metrics
        self.cluster_deployment_count = Gauge(
            'openshift_mce_cluster_deployment_count',
            'Total number of ClusterDeployments',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.cluster_deployment_status = Gauge(
            'openshift_mce_cluster_deployment_status',
            'ClusterDeployment status',
            ['cluster_name', 'name', 'namespace', 'status'],
            registry=self.registry
        )
        
        # ManagedCluster metrics
        self.managed_cluster_count = Gauge(
            'openshift_mce_managed_cluster_count',
            'Total number of ManagedClusters',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.managed_cluster_info = Info(
            'openshift_mce_managed_cluster',
            'ManagedCluster information',
            ['cluster_name', 'name', 'cluster_id'],
            registry=self.registry
        )
        
        self.managed_cluster_cpu_cores = Gauge(
            'openshift_mce_managed_cluster_cpu_cores',
            'CPU cores in managed cluster',
            ['cluster_name', 'name', 'cluster_id'],
            registry=self.registry
        )
        
        self.managed_cluster_memory_gb = Gauge(
            'openshift_mce_managed_cluster_memory_gb',
            'Memory in GB in managed cluster',
            ['cluster_name', 'name', 'cluster_id'],
            registry=self.registry
        )
        
        self.managed_cluster_node_count = Gauge(
            'openshift_mce_managed_cluster_node_count',
            'Number of nodes in managed cluster',
            ['cluster_name', 'name', 'cluster_id'],
            registry=self.registry
        )
        
        # Collection metrics
        self.collection_duration_seconds = Gauge(
            'openshift_mce_collection_duration_seconds',
            'Time taken to collect metrics',
            ['cluster_name'],
            registry=self.registry
        )
        
        self.collection_errors = Counter(
            'openshift_mce_collection_errors_total',
            'Total number of collection errors',
            ['cluster_name'],
            registry=self.registry
        )
    
    def update_metrics(self, metrics_data: MetricsData):
        """Update Prometheus metrics with collected data."""
        # Reset metrics to avoid stale data
        self._reset_metrics()
        
        # Update InfraEnv metrics
        self.infraenv_count.labels(cluster_name=self.cluster_name).set(len(metrics_data.infra_envs))
        
        # Global counters
        total_hosts = 0
        total_available = 0
        total_cpu = 0
        total_memory_mb = 0
        global_status_counts = {status: 0 for status in HostStatus}
        
        for infra_env in metrics_data.infra_envs:
            # Per-InfraEnv counters
            infraenv_total_hosts = len(infra_env.hosts)
            infraenv_available = 0
            infraenv_cpu = 0
            infraenv_memory_mb = 0
            infraenv_status_counts = {status: 0 for status in HostStatus}
            
            # InfraEnv host count
            self.infraenv_hosts.labels(
                cluster_name=self.cluster_name,
                infraenv_name=infra_env.name,
                namespace=infra_env.namespace
            ).set(infraenv_total_hosts)
            
            # Process each host
            for host in infra_env.hosts:
                total_hosts += 1
                
                # Count by status
                infraenv_status_counts[host.status] += 1
                global_status_counts[host.status] += 1
                
                # Host status
                for status in HostStatus:
                    is_current_status = 1 if host.status == status else 0
                    self.host_status.labels(
                        cluster_name=self.cluster_name,
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace,
                        status=status.value
                    ).set(is_current_status)
                
                # Check if host is available
                if host.status in [HostStatus.KNOWN, HostStatus.PREPARING_SUCCESSFUL]:
                    infraenv_available += 1
                    total_available += 1
                
                # Host resources
                if host.cpu_cores:
                    self.host_cpu_cores.labels(
                        cluster_name=self.cluster_name,
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace
                    ).set(host.cpu_cores)
                    infraenv_cpu += host.cpu_cores
                    total_cpu += host.cpu_cores
                
                if host.memory_mb:
                    self.host_memory_mb.labels(
                        cluster_name=self.cluster_name,
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace
                    ).set(host.memory_mb)
                    infraenv_memory_mb += host.memory_mb
                    total_memory_mb += host.memory_mb
                
                if host.disk_gb:
                    self.host_disk_gb.labels(
                        cluster_name=self.cluster_name,
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace
                    ).set(host.disk_gb)
            
            # Set per-InfraEnv metrics
            self.infraenv_available_hosts.labels(
                cluster_name=self.cluster_name,
                infraenv_name=infra_env.name,
                namespace=infra_env.namespace
            ).set(infraenv_available)
            
            # Set per-InfraEnv status counts
            for status, count in infraenv_status_counts.items():
                self.infraenv_hosts_by_status.labels(
                    cluster_name=self.cluster_name,
                    infraenv_name=infra_env.name,
                    namespace=infra_env.namespace,
                    status=status.value
                ).set(count)
            
            self.infraenv_cpu_cores.labels(
                cluster_name=self.cluster_name,
                infraenv_name=infra_env.name,
                namespace=infra_env.namespace
            ).set(infraenv_cpu)
            
            self.infraenv_memory_gb.labels(
                cluster_name=self.cluster_name,
                infraenv_name=infra_env.name,
                namespace=infra_env.namespace
            ).set(infraenv_memory_mb / 1024 if infraenv_memory_mb > 0 else 0)
        
        # Update global aggregate metrics
        self.total_hosts.labels(cluster_name=self.cluster_name).set(total_hosts)
        self.total_available_hosts.labels(cluster_name=self.cluster_name).set(total_available)
        self.total_cpu_cores.labels(cluster_name=self.cluster_name).set(total_cpu)
        self.total_memory_gb.labels(cluster_name=self.cluster_name).set(
            total_memory_mb / 1024 if total_memory_mb > 0 else 0
        )
        
        # Set global status counts
        for status, count in global_status_counts.items():
            self.total_hosts_by_status.labels(
                cluster_name=self.cluster_name,
                status=status.value
            ).set(count)
        
        # Update ClusterDeployment metrics
        self.cluster_deployment_count.labels(cluster_name=self.cluster_name).set(
            len(metrics_data.cluster_deployments)
        )
        
        for cd in metrics_data.cluster_deployments:
            if cd.status:
                self.cluster_deployment_status.labels(
                    cluster_name=self.cluster_name,
                    name=cd.name,
                    namespace=cd.namespace,
                    status=cd.status
                ).set(1)
        
        # Update ManagedCluster metrics
        self.managed_cluster_count.labels(cluster_name=self.cluster_name).set(
            len(metrics_data.managed_clusters)
        )
        
        for mc in metrics_data.managed_clusters:
            self.managed_cluster_info.labels(
                cluster_name=self.cluster_name,
                name=mc.name,
                cluster_id=mc.cluster_id or 'unknown'
            ).info({
                'vendor': mc.vendor or 'unknown',
                'cloud': mc.cloud or 'unknown',
                'version': mc.version or 'unknown'
            })
            
            if mc.cpu_cores:
                self.managed_cluster_cpu_cores.labels(
                    cluster_name=self.cluster_name,
                    name=mc.name,
                    cluster_id=mc.cluster_id or 'unknown'
                ).set(mc.cpu_cores)
            
            if mc.memory_gb:
                self.managed_cluster_memory_gb.labels(
                    cluster_name=self.cluster_name,
                    name=mc.name,
                    cluster_id=mc.cluster_id or 'unknown'
                ).set(mc.memory_gb)
            
            if mc.node_count:
                self.managed_cluster_node_count.labels(
                    cluster_name=self.cluster_name,
                    name=mc.name,
                    cluster_id=mc.cluster_id or 'unknown'
                ).set(mc.node_count)
    
    def _reset_metrics(self):
        """Reset all metrics to avoid stale data."""
        # This is handled by Prometheus client library when setting new values
        pass
    
    def collect_and_update(self):
        """Collect metrics and update Prometheus metrics."""
        start_time = time.time()
        
        try:
            metrics_data = self.collector.collect_all_metrics()
            self.update_metrics(metrics_data)
            
            duration = time.time() - start_time
            self.collection_duration_seconds.labels(cluster_name=self.cluster_name).set(duration)
            
            logger.info(f"Metrics updated successfully in {duration:.2f} seconds for cluster {self.cluster_name}")
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            self.collection_errors.labels(cluster_name=self.cluster_name).inc()
            raise
    
    def generate_metrics(self) -> bytes:
        """Generate metrics in Prometheus format."""
        return generate_latest(self.registry)