# Fleet Monitoring — External Stack

Fleet infrastructure metrics, dashboards, and alerting are handled by a self-hosted
Prometheus/Grafana/Alertmanager stack. No fleet telemetry leaves the customer network.

## What fleetent provides

| Endpoint | Purpose | Notes |
|----------|---------|-------|
| `GET /health` | Process liveness (up/down) | Used by load balancers and uptime checks |
| Observability traces | Agent-run telemetry (tool calls, token usage, errors) | Internal, agent-domain only |

## What the external stack provides

| Component | Role |
|-----------|------|
| **node_exporter** | Host metrics — CPU, memory, disk, network |
| **cAdvisor** | Container metrics — per-container resource usage |
| **Prometheus** | Scrape, store, and query metrics (self-hosted, in-network) |
| **Grafana** | Dashboards — fleet health, resource utilization |
| **Alertmanager** | Alert routing — email, Slack, PagerDuty, webhook |

## Quick setup

### 1. node_exporter (one per host)

```bash
docker run -d --name node-exporter \
  --net="host" --pid="host" \
  -v "/:/host:ro,rslave" \
  quay.io/prometheus/node-exporter:latest \
  --path.rootfs=/host
```

### 2. cAdvisor (one per host running containers)

```bash
docker run -d --name cadvisor \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --publish=8080:8080 \
  gcr.io/cadvisor/cadvisor:latest
```

### 3. Prometheus — minimal `prometheus.yml`

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: node
    static_configs:
      - targets: ['<host>:9100']   # node_exporter

  - job_name: cadvisor
    static_configs:
      - targets: ['<host>:8080']   # cAdvisor

  - job_name: fleetent_health
    metrics_path: /health
    # /health returns JSON; use blackbox_exporter for probe-based alerting
    # or rely on node/cadvisor for process-level signals
    static_configs:
      - targets: ['<fleetent-host>:8765']
```

### 4. Alertmanager

Point Prometheus at your Alertmanager instance and define alert rules in Prometheus
rule files. Example rule for host CPU:

```yaml
groups:
  - name: fleet
    rules:
      - alert: HighCPU
        expr: 100 - (avg by(instance)(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100) > 85
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High CPU on {{ $labels.instance }}"
```

### 5. Grafana

Import community dashboards:
- **Node Exporter Full**: dashboard ID `1860`
- **cAdvisor**: dashboard ID `14282`

Add your Prometheus instance as a data source and point Grafana at it.

## Data sovereignty

All components run inside the customer's network. No metrics are sent to any external
service. Use official Docker images (available on Docker Hub / quay.io / gcr.io) and
pin versions for reproducibility.
