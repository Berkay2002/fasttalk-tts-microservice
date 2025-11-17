"""
Standalone monitoring server entrypoint for the TTS service.

Allows the monitoring API to be launched independently, mirroring the other
microservices for consistency.
"""

from __future__ import annotations

import argparse
import sys

from app.monitoring.service_monitor import MonitoringServer, ServiceMonitor
from app.utils.config import load_config


def run_monitoring_service() -> None:
    parser = argparse.ArgumentParser(description="FastTalk TTS Monitoring Server")
    parser.add_argument("--port", type=int, help="Monitoring server port (default: config value)")
    parser.add_argument("--host", type=str, help="Monitoring host (default: config value)")
    parser.add_argument("--debug", action="store_true", help="Run Flask in debug mode")
    args = parser.parse_args()

    try:
        config = load_config()
        host = args.host or config.monitoring_host
        port = args.port or config.monitoring_port

        monitor = ServiceMonitor()
        server = MonitoringServer(host=host, port=port, monitor=monitor)

        print(f"Starting TTS monitoring server on http://{host}:{port}")
        print(f"Health:   http://{host}:{port}/health")
        print(f"Metrics:  http://{host}:{port}/metrics")
        print(f"Info:     http://{host}:{port}/info")
        server.run(debug=args.debug)
    except KeyboardInterrupt:
        print("Monitoring server stopped by user.")
    except Exception as exc:
        print(f"Failed to start monitoring server: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    run_monitoring_service()
