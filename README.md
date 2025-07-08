# OpenShift MCE Metrics Exporter

A Prometheus exporter for OpenShift MultiCluster Engine (MCE) that collects and exposes metrics about infrastructure inventory including InfraEnvs, Hosts, ClusterDeployments, and ManagedClusters.

## Overview

This exporter provides real-time metrics about your OpenShift infrastructure managed by MCE (MultiCluster Engine), Assisted Installer, and HyperShift. It exposes Prometheus-compatible metrics that can be scraped and visualized in Grafana.

### Key Features

- 📊 **InfraEnv Metrics**: Track infrastructure environments and their associated hosts
- 🖥️ **Host Inventory**: Monitor CPU cores, memory, disk space, and host status
- 🚀 **Cluster Deployment Status**: Track ClusterDeployment resources from Hive
- 🌐 **Managed Clusters**: Monitor clusters managed by MCE
- 📈 **Prometheus Compatible**: Native Prometheus metrics format
- 🎨 **Grafana Ready**: Pre-built dashboards for visualization
- 🐍 **Pydantic Models**: Type-safe data validation

## Metrics Exposed

### InfraEnv Metrics
- `openshift_mce_infraenv_count` - Total number of InfraEnvs
- `openshift_mce_infraenv_hosts` - Number of hosts per InfraEnv

### Host Metrics
- `openshift_mce_host_status` - Host status (discovering, known, installed, etc.)
- `openshift_mce_host_cpu_cores` - CPU cores per host
- `openshift_mce_host_memory_mb` - Memory in MB per host
- `openshift_mce_host_disk_gb` - Disk space in GB per host

### Aggregate Metrics
- `openshift_mce_total_hosts` - Total hosts across all InfraEnvs
- `openshift_mce_total_available_hosts` - Total available hosts
- `openshift_mce_total_cpu_cores` - Total CPU cores across all hosts
- `openshift_mce_total_memory_gb` - Total memory in GB across all hosts

### Cluster Metrics
- `openshift_mce_cluster_deployment_count` - Total ClusterDeployments
- `openshift_mce_cluster_deployment_status` - ClusterDeployment status
- `openshift_mce_managed_cluster_count` - Total ManagedClusters
- `openshift_mce_managed_cluster_cpu_cores` - CPU cores per managed cluster
- `openshift_mce_managed_cluster_memory_gb` - Memory per managed cluster

## Requirements

- OpenShift 4.10+ with MCE operator installed
- Python 3.11+
- Kubernetes API access with appropriate RBAC permissions
- Prometheus for metrics collection
- Grafana for visualization (optional)

## Installation

### Quick Start with Helm (Recommended)

```bash
# Clone the repository
git clone https://github.com/your-org/openshift-mce-exporter.git
cd openshift-mce-exporter

# Deploy using Helm
helm install mce-exporter ./helm-chart \
  --namespace openshift-mce-monitoring \
  --create-namespace
```

### Manual Deployment

1. **Create namespace and RBAC**:
```bash
oc create namespace openshift-mce-monitoring
oc apply -f config/rbac.yaml -n openshift-mce-monitoring
```

2. **Deploy the exporter**:
```bash
oc apply -f deploy/ -n openshift-mce-monitoring
```

3. **Verify deployment**:
```bash
oc get pods -n openshift-mce-monitoring
oc logs -f deployment/mce-metrics-exporter -n openshift-mce-monitoring
```

## Configuration

The exporter can be configured using environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `METRICS_PORT` | Port to expose metrics | `8080` |
| `COLLECTION_INTERVAL` | Interval between metric collections (seconds) | `60` |
| `IN_CLUSTER` | Whether running inside Kubernetes cluster | `true` |
| `LOG_LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO` |

### Example ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: mce-exporter-config
data:
  METRICS_PORT: "8080"
  COLLECTION_INTERVAL: "30"
  LOG_LEVEL: "INFO"
```

## Development

### Local Development

1. **Clone and setup**:
```bash
git clone https://github.com/your-org/openshift-mce-exporter.git
cd openshift-mce-exporter
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

2. **Run locally**:
```bash
# Export your kubeconfig
export KUBECONFIG=/path/to/your/kubeconfig
export IN_CLUSTER=false

# Run the exporter
python src/main.py
```

3. **Run tests**:
```bash
pytest tests/ -v --cov=src
```

### Building Container Image

```bash
# Build locally
docker build -t openshift-mce-exporter:latest .

# Or use make
make build REGISTRY=your-registry IMAGE_TAG=v1.0.0
```

## Prometheus Configuration

Add the following job to your Prometheus configuration:

```yaml
scrape_configs:
  - job_name: 'mce-metrics'
    kubernetes_sd_configs:
      - role: service
        namespaces:
          names:
            - openshift-mce-monitoring
    relabel_configs:
      - source_labels: [__meta_kubernetes_service_name]
        action: keep
        regex: mce-metrics-exporter
```

Or use the included ServiceMonitor for Prometheus Operator:

```bash
oc apply -f deploy/servicemonitor.yaml
```

## Grafana Dashboards

Import the pre-built dashboards from the `grafana/dashboards/` directory:

1. **Infrastructure Overview**: Overall infrastructure capacity and utilization
2. **Host Inventory**: Detailed host status and resource allocation
3. **Cluster Status**: ClusterDeployment and ManagedCluster monitoring

### Importing Dashboards

```bash
# Using Grafana API
curl -X POST http://grafana.example.com/api/dashboards/db \
  -H "Authorization: Bearer $GRAFANA_API_KEY" \
  -H "Content-Type: application/json" \
  -d @grafana/dashboards/infrastructure-overview.json
```

## Troubleshooting

### Common Issues

1. **Permission Denied Errors**:
   - Ensure the ServiceAccount has proper RBAC permissions
   - Check ClusterRole and ClusterRoleBinding are applied

2. **No Metrics Exposed**:
   - Check logs: `oc logs deployment/mce-metrics-exporter`
   - Verify InfraEnv resources exist: `oc get infraenv -A`
   - Check connectivity to Kubernetes API

3. **High Memory Usage**:
   - Increase collection interval
   - Adjust resource limits in deployment

### Debug Mode

Enable debug logging:
```bash
oc set env deployment/mce-metrics-exporter LOG_LEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Development Guidelines

- Use type hints and Pydantic models
- Add unit tests for new features
- Follow PEP 8 style guide
- Update documentation

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────┐
│   OpenShift     │────▶│  MCE Exporter    │────▶│ Prometheus  │
│   Kubernetes    │     │                  │     │             │
│      API        │     │ - Collector      │     │             │
└─────────────────┘     │ - Pydantic       │     └─────────────┘
                        │ - Flask Server   │              │
                        └──────────────────┘              ▼
                                                   ┌─────────────┐
                                                   │   Grafana   │
                                                   └─────────────┘
```

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Support

- 📧 Email: your-team@example.com
- 💬 Slack: #mce-monitoring
- 🐛 Issues: [GitHub Issues](https://github.com/your-org/openshift-mce-exporter/issues)

## Acknowledgments

- OpenShift MCE team for the excellent operator
- Prometheus community for the client library
- Contributors and maintainers

---

Made with ❤️ by the SRE Team