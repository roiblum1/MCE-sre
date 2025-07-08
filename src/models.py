from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


class HostStatus(str, Enum):
    DISCOVERING = "discovering"
    KNOWN = "known"
    DISCONNECTED = "disconnected"
    INSUFFICIENT = "insufficient"
    DISABLED = "disabled"
    PREPARING = "preparing"
    PREPARING_FAILED = "preparing-failed"
    PREPARING_SUCCESSFUL = "preparing-successful"
    PENDING_FOR_INPUT = "pending-for-input"
    INSTALLING = "installing"
    INSTALLING_IN_PROGRESS = "installing-in-progress"
    INSTALLING_PENDING_USER_ACTION = "installing-pending-user-action"
    RESETTING = "resetting"
    RESETTING_PENDING_USER_ACTION = "resetting-pending-user-action"
    INSTALLED = "installed"
    ERROR = "error"
    ADDED_TO_EXISTING_CLUSTER = "added-to-existing-cluster"


class Host(BaseModel):
    id: str
    hostname: Optional[str] = None
    status: HostStatus
    status_info: Optional[str] = None
    cpu_cores: Optional[int] = Field(None, alias="cpuCores")
    memory_mb: Optional[int] = Field(None, alias="memoryMB")
    disk_gb: Optional[int] = Field(None, alias="diskGB")
    architecture: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    cluster_id: Optional[str] = Field(None, alias="clusterId")
    
    class Config:
        populate_by_name = True


class InfraEnv(BaseModel):
    name: str
    namespace: str
    uid: str
    hosts: List[Host] = []
    created_at: Optional[datetime] = Field(None, alias="createdAt")
    
    class Config:
        populate_by_name = True


class ClusterDeployment(BaseModel):
    name: str
    namespace: str
    uid: str
    status: Optional[str] = None
    base_domain: Optional[str] = Field(None, alias="baseDomain")
    cluster_name: Optional[str] = Field(None, alias="clusterName")
    platform: Optional[str] = None
    agent_cluster_install_ref: Optional[str] = Field(None, alias="agentClusterInstallRef")
    
    class Config:
        populate_by_name = True


class ManagedCluster(BaseModel):
    name: str
    namespace: Optional[str] = None
    uid: str
    status: Optional[Dict[str, Any]] = None
    cluster_id: Optional[str] = Field(None, alias="clusterId")
    vendor: Optional[str] = None
    cloud: Optional[str] = None
    version: Optional[str] = None
    cpu_cores: Optional[int] = 0
    memory_gb: Optional[int] = 0
    node_count: Optional[int] = 0
    
    class Config:
        populate_by_name = True


class MetricsData(BaseModel):
    infra_envs: List[InfraEnv] = []
    cluster_deployments: List[ClusterDeployment] = []
    managed_clusters: List[ManagedCluster] = []
    collection_timestamp: datetime = Field(default_factory=datetime.utcnow)