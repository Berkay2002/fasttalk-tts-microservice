"""
Main entry point for the FastTalk TTS microservice.

Provides a CLI interface consistent with the other microservices so orchestration
and local development share the same workflow.
"""

from __future__ import annotations

import argparse
import logging
import sys
from textwrap import dedent

from app.core.websocket_launcher import WebSocketLauncher
from app.monitoring.service_monitor import MonitoringServer, ServiceMonitor
from app.utils.config import Config
from app.utils.logger import get_logger

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)

logger = get_logger(__name__)


def _print_config(config: Config) -> None:
    banner = "=" * 60
    print(dedent(
        f"""
        {banner}
        TTS Service Configuration
        {banner}
        """
    ).strip())
    for key, value in config.to_dict().items():
        print(f"{key:30s}: {value}")
    print(banner)


def main() -> None:
    parser = argparse.ArgumentParser(description="FastTalk TTS Service")
    parser.add_argument("mode", choices=["websocket", "config"], help="Operating mode")
    parser.add_argument("--host", type=str, help="Override server host")
    parser.add_argument("--port", type=int, help="Override server port")
    parser.add_argument("--monitoring-port", type=int, help="Override monitoring port")
    parser.add_argument("--monitoring-host", type=str, help="Override monitoring host")
    parser.add_argument("--voice", type=str, help="Default voice override")
    parser.add_argument("--language", type=str, help="Default language override")
    parser.add_argument("--speed", type=float, help="Default speed override")
    parser.add_argument("--log-level", type=str, help="Logging level override")
    parser.add_argument("--backend", type=str, choices=["kokoro", "chatterbox"], help="Backend engine")
    parser.add_argument("--chatterbox-device", type=str, help="Device for Chatterbox (cuda/cpu)")
    parser.add_argument("--show", action="store_true", help="Display configuration (config mode)")

    args = parser.parse_args()

    config = Config()

    if args.host:
        config.host = args.host
    if args.port:
        config.port = args.port
    if args.monitoring_host:
        config.monitoring_host = args.monitoring_host
    if args.monitoring_port:
        config.monitoring_port = args.monitoring_port
    if args.voice:
        config.default_voice = args.voice
    if args.language:
        config.default_language = args.language
    if args.speed:
        config.default_speed = args.speed
    if args.log_level:
        config.log_level = args.log_level
    if args.backend:
        config.backend = args.backend
    if args.chatterbox_device:
        config.chatterbox_device = args.chatterbox_device

    logging.getLogger().setLevel(getattr(logging, config.log_level.upper(), logging.INFO))

    if args.mode == "config":
        if args.show:
            _print_config(config)
        else:
            parser.print_help()
        return

    if args.mode == "websocket":
        monitor = ServiceMonitor()
        monitoring_server = MonitoringServer(
            host=config.monitoring_host,
            port=config.monitoring_port,
            monitor=monitor,
        )
        monitoring_server.start()
        logger.info(
            "Monitoring server started",
            host=config.monitoring_host,
            port=config.monitoring_port,
        )

        launcher = WebSocketLauncher(config=config, monitor=monitor)
        launcher.start()


if __name__ == "__main__":
    main()
