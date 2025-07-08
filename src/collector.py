import logging
from typing import List, Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException
import requests
from models import (
    Host, InfraEnv, ClusterDeployment, ManagedCluster, 
    MetricsData, HostStatus
)

logger = logging.getLogger(__name__)


class OpenShiftMetricsCollector:
    def __init__(self, in_cluster: bool = True):
        """Initialize the OpenShift metrics collector.
        
        Args:
            in_cluster: Whether running inside the cluster or not
        """
        if in_cluster:
            config.load_incluster_config()
        else:
            config.load_kube_config()
        
        self.api = client.ApiClient()
        self.custom_api = client.CustomObjectsApi(self.api)
        self.core_api = client.CoreV1Api(self.api)
        
    def collect_infra_envs(self) -> List[InfraEnv]:
        """Collect all InfraEnv resources and their associated hosts."""
        infra_envs = []
        
        try:
            # Get all InfraEnvs across all namespaces
            infra_env_list = self.custom_api.list_cluster_custom_object(
                group="agent-install.openshift.io",
                version="v1beta1",
                plural="infraenvs"
            )
            
            for item in infra_env_list.get('items', []):
                metadata = item.get('metadata', {})
                spec = item.get('spec', {})
                status = item.get('status', {})
                
                infra_env = InfraEnv(
                    name=metadata.get('name'),
                    namespace=metadata.get('namespace'),
                    uid=metadata.get('uid'),
                    created_at=metadata.get('creationTimestamp')
                )
                
                # Collect hosts for this InfraEnv
                hosts = self._collect_hosts_for_infra_env(
                    infra_env.name, 
                    infra_env.namespace
                )
                infra_env.hosts = hosts
                
                infra_envs.append(infra_env)
                
        except ApiException as e:
            logger.error(f"Error collecting InfraEnvs: {e}")
            
        return infra_envs
    
    def _collect_hosts_for_infra_env(self, infra_env_name: str, namespace: str) -> List[Host]:
        """Collect all Agent (host) resources for a specific InfraEnv."""
        hosts = []
        
        try:
            # Get agents in the namespace
            agents = self.custom_api.list_namespaced_custom_object(
                group="agent-install.openshift.io",
                version="v1beta1",
                namespace=namespace,
                plural="agents"
            )
            
            for agent in agents.get('items', []):
                metadata = agent.get('metadata', {})
                spec = agent.get('spec', {})
                status = agent.get('status', {})
                
                # Check if this agent belongs to the InfraEnv
                labels = metadata.get('labels', {})
                if labels.get('infraenvs.agent-install.openshift.io') != infra_env_name:
                    continue
                
                inventory = status.get('inventory', {})
                
                # Extract host information
                host = Host(
                    id=metadata.get('name'),
                    hostname=inventory.get('hostname'),
                    status=status.get('debugInfo', {}).get('state', HostStatus.DISCOVERING),
                    status_info=status.get('debugInfo', {}).get('stateInfo'),
                    cpu_cores=inventory.get('cpu', {}).get('count'),
                    memory_mb=self._bytes_to_mb(inventory.get('memory', {}).get('physicalBytes')),
                    disk_gb=self._calculate_total_disk_gb(inventory.get('disks', [])),
                    architecture=inventory.get('cpu', {}).get('architecture'),
                    vendor=inventory.get('systemVendor', {}).get('manufacturer'),
                    model=inventory.get('systemVendor', {}).get('productName'),
                    cluster_id=spec.get('clusterDeploymentName', {}).get('name')
                )
                
                hosts.append(host)
                
        except ApiException as e:
            logger.error(f"Error collecting hosts for InfraEnv {infra_env_name}: {e}")
            
        return hosts
    
    def collect_cluster_deployments(self) -> List[ClusterDeployment]:
        """Collect all ClusterDeployment resources."""
        cluster_deployments = []
        
        try:
            cd_list = self.custom_api.list_cluster_custom_object(
                group="hive.openshift.io",
                version="v1",
                plural="clusterdeployments"
            )
            
            for item in cd_list.get('items', []):
                metadata = item.get('metadata', {})
                spec = item.get('spec', {})
                status = item.get('status', {})
                
                cd = ClusterDeployment(
                    name=metadata.get('name'),
                    namespace=metadata.get('namespace'),
                    uid=metadata.get('uid'),
                    status=status.get('conditions', [{}])[0].get('type') if status.get('conditions') else None,
                    base_domain=spec.get('baseDomain'),
                    cluster_name=spec.get('clusterName'),
                    platform=spec.get('platform', {}).get('type'),
                    agent_cluster_install_ref=spec.get('clusterInstallRef', {}).get('name')
                )
                
                cluster_deployments.append(cd)
                
        except ApiException as e:
            logger.error(f"Error collecting ClusterDeployments: {e}")
            
        return cluster_deployments
    
    def collect_managed_clusters(self) -> List[ManagedCluster]:
        """Collect all ManagedCluster resources from MCE."""
        managed_clusters = []
        
        try:
            mc_list = self.custom_api.list_cluster_custom_object(
                group="cluster.open-cluster-management.io",
                version="v1",
                plural="managedclusters"
            )
            
            for item in mc_list.get('items', []):
                metadata = item.get('metadata', {})
                status = item.get('status', {})
                
                # Extract cluster info from labels and status
                labels = metadata.get('labels', {})
                
                mc = ManagedCluster(
                    name=metadata.get('name'),
                    namespace=metadata.get('namespace'),
                    uid=metadata.get('uid'),
                    status=status,
                    cluster_id=labels.get('clusterID'),
                    vendor=labels.get('vendor'),
                    cloud=labels.get('cloud'),
                    version=status.get('version', {}).get('kubernetes'),
                    cpu_cores=self._extract_cluster_capacity(item, 'cpu'),
                    memory_gb=self._extract_cluster_capacity(item, 'memory'),
                    node_count=self._extract_node_count(item)
                )
                
                managed_clusters.append(mc)
                
        except ApiException as e:
            logger.error(f"Error collecting ManagedClusters: {e}")
            
        return managed_clusters
    
    def collect_all_metrics(self) -> MetricsData:
        """Collect all metrics from the cluster."""
        logger.info("Starting metrics collection...")
        
        metrics = MetricsData()
        
        # Collect InfraEnvs and their hosts
        logger.info("Collecting InfraEnvs...")
        metrics.infra_envs = self.collect_infra_envs()
        
        # Collect ClusterDeployments
        logger.info("Collecting ClusterDeployments...")
        metrics.cluster_deployments = self.collect_cluster_deployments()
        
        # Collect ManagedClusters
        logger.info("Collecting ManagedClusters...")
        metrics.managed_clusters = self.collect_managed_clusters()
        
        logger.info("Metrics collection completed")
        return metrics
    
    @staticmethod
    def _bytes_to_mb(bytes_value: Optional[int]) -> Optional[int]:
        """Convert bytes to megabytes."""
        if bytes_value is None:
            return None
        return int(bytes_value / (1024 * 1024))
    
    @staticmethod
    def _calculate_total_disk_gb(disks: List[Dict[str, Any]]) -> Optional[int]:
        """Calculate total disk space in GB from disk list."""
        if not disks:
            return None
        
        total_bytes = sum(disk.get('sizeBytes', 0) for disk in disks)
        return int(total_bytes / (1024 * 1024 * 1024))
    
    def _extract_cluster_capacity(self, managed_cluster: Dict[str, Any], resource: str) -> int:
        """Extract cluster capacity for CPU or memory."""
        # This would need to query the cluster's nodes to get actual capacity
        # For now, returning 0 as placeholder
        return 0
    
    def _extract_node_count(self, managed_cluster: Dict[str, Any]) -> int:
        """Extract node count from managed cluster."""
        # This would need to query the cluster's nodes
        # For now, returning 0 as placeholder
        return 0