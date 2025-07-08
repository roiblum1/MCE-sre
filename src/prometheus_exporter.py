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
        self._setup_metrics()
        
    def _setup_metrics(self):
        """Setup Prometheus metrics."""
        # InfraEnv metrics
        self.infraenv_count = Gauge(
            'openshift_mce_infraenv_count',
            'Total number of InfraEnvs',
            registry=self.registry
        )
        
        self.infraenv_hosts = Gauge(
            'openshift_mce_infraenv_hosts',
            'Number of hosts in InfraEnv',
            ['infraenv_name', 'namespace'],
            registry=self.registry
        )
        
        # Host metrics
        self.host_status = Gauge(
            'openshift_mce_host_status',
            'Host status (1 if in this status, 0 otherwise)',
            ['host_id', 'hostname', 'infraenv', 'namespace', 'status'],
            registry=self.registry
        )
        
        self.host_cpu_cores = Gauge(
            'openshift_mce_host_cpu_cores',
            'Number of CPU cores on host',
            ['host_id', 'hostname', 'infraenv', 'namespace'],
            registry=self.registry
        )
        
        self.host_memory_mb = Gauge(
            'openshift_mce_host_memory_mb',
            'Memory in MB on host',
            ['host_id', 'hostname', 'infraenv', 'namespace'],
            registry=self.registry
        )
        
        self.host_disk_gb = Gauge(
            'openshift_mce_host_disk_gb',
            'Disk space in GB on host',
            ['host_id', 'hostname', 'infraenv', 'namespace'],
            registry=self.registry
        )
        
        # Aggregate metrics
        self.total_hosts = Gauge(
            'openshift_mce_total_hosts',
            'Total number of hosts across all InfraEnvs',
            registry=self.registry
        )
        
        self.total_available_hosts = Gauge(
            'openshift_mce_total_available_hosts',
            'Total number of available hosts',
            registry=self.registry
        )
        
        self.total_cpu_cores = Gauge(
            'openshift_mce_total_cpu_cores',
            'Total CPU cores across all hosts',
            registry=self.registry
        )
        
        self.total_memory_gb = Gauge(
            'openshift_mce_total_memory_gb',
            'Total memory in GB across all hosts',
            registry=self.registry
        )
        
        # ClusterDeployment metrics
        self.cluster_deployment_count = Gauge(
            'openshift_mce_cluster_deployment_count',
            'Total number of ClusterDeployments',
            registry=self.registry
        )
        
        self.cluster_deployment_status = Gauge(
            'openshift_mce_cluster_deployment_status',
            'ClusterDeployment status',
            ['name', 'namespace', 'status'],
            registry=self.registry
        )
        
        # ManagedCluster metrics
        self.managed_cluster_count = Gauge(
            'openshift_mce_managed_cluster_count',
            'Total number of ManagedClusters',
            registry=self.registry
        )
        
        self.managed_cluster_info = Info(
            'openshift_mce_managed_cluster',
            'ManagedCluster information',
            ['name', 'cluster_id'],
            registry=self.registry
        )
        
        self.managed_cluster_cpu_cores = Gauge(
            'openshift_mce_managed_cluster_cpu_cores',
            'CPU cores in managed cluster',
            ['name', 'cluster_id'],
            registry=self.registry
        )
        
        self.managed_cluster_memory_gb = Gauge(
            'openshift_mce_managed_cluster_memory_gb',
            'Memory in GB in managed cluster',
            ['name', 'cluster_id'],
            registry=self.registry
        )
        
        self.managed_cluster_node_count = Gauge(
            'openshift_mce_managed_cluster_node_count',
            'Number of nodes in managed cluster',
            ['name', 'cluster_id'],
            registry=self.registry
        )
        
        # Collection metrics
        self.collection_duration_seconds = Gauge(
            'openshift_mce_collection_duration_seconds',
            'Time taken to collect metrics',
            registry=self.registry
        )
        
        self.collection_errors = Counter(
            'openshift_mce_collection_errors_total',
            'Total number of collection errors',
            registry=self.registry
        )
    
    def update_metrics(self, metrics_data: MetricsData):
        """Update Prometheus metrics with collected data."""
        # Reset metrics to avoid stale data
        self._reset_metrics()
        
        # Update InfraEnv metrics
        self.infraenv_count.set(len(metrics_data.infra_envs))
        
        total_hosts = 0
        total_available = 0
        total_cpu = 0
        total_memory_mb = 0
        
        for infra_env in metrics_data.infra_envs:
            # InfraEnv host count
            self.infraenv_hosts.labels(
                infraenv_name=infra_env.name,
                namespace=infra_env.namespace
            ).set(len(infra_env.hosts))
            
            # Process each host
            for host in infra_env.hosts:
                total_hosts += 1
                
                # Host status
                for status in HostStatus:
                    is_current_status = 1 if host.status == status else 0
                    self.host_status.labels(
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace,
                        status=status.value
                    ).set(is_current_status)
                
                # Check if host is available
                if host.status in [HostStatus.KNOWN, HostStatus.PREPARING_SUCCESSFUL]:
                    total_available += 1
                
                # Host resources
                if host.cpu_cores:
                    self.host_cpu_cores.labels(
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace
                    ).set(host.cpu_cores)
                    total_cpu += host.cpu_cores
                
                if host.memory_mb:
                    self.host_memory_mb.labels(
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace
                    ).set(host.memory_mb)
                    total_memory_mb += host.memory_mb
                
                if host.disk_gb:
                    self.host_disk_gb.labels(
                        host_id=host.id,
                        hostname=host.hostname or 'unknown',
                        infraenv=infra_env.name,
                        namespace=infra_env.namespace
                    ).set(host.disk_gb)
        
        # Update aggregate metrics
        self.total_hosts.set(total_hosts)
        self.total_available_hosts.set(total_available)
        self.total_cpu_cores.set(total_cpu)
        self.total_memory_gb.set(total_memory_mb / 1024 if total_memory_mb > 0 else 0)
        
        # Update ClusterDeployment metrics
        self.cluster_deployment_count.set(len(metrics_data.cluster_deployments))
        
        for cd in metrics_data.cluster_deployments:
            if cd.status:
                self.cluster_deployment_status.labels(
                    name=cd.name,
                    namespace=cd.namespace,
                    status=cd.status
                ).set(1)
        
        # Update ManagedCluster metrics
        self.managed_cluster_count.set(len(metrics_data.managed_clusters))
        
        for mc in metrics_data.managed_clusters:
            self.managed_cluster_info.labels(
                name=mc.name,
                cluster_id=mc.cluster_id or 'unknown'
            ).info({
                'vendor': mc.vendor or 'unknown',
                'cloud': mc.cloud or 'unknown',
                'version': mc.version or 'unknown'
            })
            
            if mc.cpu_cores:
                self.managed_cluster_cpu_cores.labels(
                    name=mc.name,
                    cluster_id=mc.cluster_id or 'unknown'
                ).set(mc.cpu_cores)
            
            if mc.memory_gb:
                self.managed_cluster_memory_gb.labels(
                    name=mc.name,
                    cluster_id=mc.cluster_id or 'unknown'
                ).set(mc.memory_gb)
            
            if mc.node_count:
                self.managed_cluster_node_count.labels(
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
            self.collection_duration_seconds.set(duration)
            
            logger.info(f"Metrics updated successfully in {duration:.2f} seconds")
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
            self.collection_errors.inc()
            raise
    
    def generate_metrics(self) -> bytes:
        """Generate metrics in Prometheus format."""
        return generate_latest(self.registry)