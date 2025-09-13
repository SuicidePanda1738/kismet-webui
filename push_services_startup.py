#!/usr/bin/env python3
"""
Push Services Startup Script
Automatically starts all configured push services on system boot
"""

import os
import sys
import time
import logging
from pathlib import Path
import socket
from contextlib import closing

# Add parent directory to path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from push_service_manager import push_service_manager
from app import app, db
from models import PushService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

PUSH_DIR = BASE_DIR / "push_services"

def _tcp_ready(host: str, port: int, timeout_s: float = 1.5) -> bool:
    """Return True if TCP socket is connectable."""
    try:
        with closing(socket.create_connection((host, port), timeout=timeout_s)):
            return True
    except OSError:
        return False

def wait_for_port(host: str, port: int, label: str, tries: int = 60, delay: float = 1.0):
    """Wait until a TCP port is accepting connections."""
    for i in range(1, tries + 1):
        if _tcp_ready(host, port):
            logger.info("%s is up at %s:%d", label, host, port)
            return True
        logger.info("Waiting for %s at %s:%d... (%d/%d)", label, host, port, i, tries)
        time.sleep(delay)
    logger.warning("Timed out waiting for %s at %s:%d", label, host, port)
    return False

def wait_for_gpsd_if_needed(services):
    """If any service includes a GPS API key, wait for gpsd on localhost:2947."""
    any_gps = any(getattr(s, "gps_api_key", None) for s in services)
    if not any_gps:
        return
    logger.info("GPS-enabled services detected; waiting for gpsd on 127.0.0.1:2947")
    wait_for_port("127.0.0.1", 2947, "gpsd")

def cleanup_stale_pids():
    """Clean up any stale PID files from previous runs."""
    PUSH_DIR.mkdir(exist_ok=True)
    for pid_file in PUSH_DIR.glob("*.pid"):
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)  # raises if not running
        except (ProcessLookupError, ValueError, OSError):
            try:
                pid_file.unlink()
                logger.info("Removed stale PID file: %s", pid_file.name)
            except Exception:
                pass

def start_all_services():
    """Start all configured push services."""
    logger.info("Starting push services...")

    cleanup_stale_pids()

    with app.app_context():
        try:
            services = PushService.query.all()
            if not services:
                logger.info("No push services configured")
                return

            # 1) readiness waits
            # gpsd (if needed)
            wait_for_gpsd_if_needed(services)

            # capture port on each unique host
            hosts = sorted({(getattr(s, "kismet_ip", None) or "").strip() for s in services if getattr(s, "kismet_ip", None)})
            hosts = [h for h in hosts if h]
            if hosts:
                logger.info("Waiting for Kismet capture port on: %s", ", ".join(hosts))
            for host in hosts:
                wait_for_port(host, 2501, "Kismet capture port")

            logger.info("Found %d configured services", len(services))

            # 2) ensure scripts exist and start them
            for service in services:
                logger.info("Processing service: %s", service.name)
                script_path = PUSH_DIR / f"{service.name}.sh"

                if not script_path.exists():
                    logger.info("Script missing for %s; recreating from DB...", service.name)
                    service_data = {
                        "name": service.name,
                        "service_type": service.service_type.replace(" + GPS", ""),  # normalize label
                        "adapter": service.adapter,
                        "sensor": service.sensor,
                        "kismet_ip": service.kismet_ip,
                        "api_key": service.api_key,
                        "gps_api_key": service.gps_api_key,
                    }
                    try:
                        push_service_manager.create_push_service_script(service_data)
                        logger.info("Recreated script for %s", service.name)
                    except Exception as e:
                        logger.error("Failed to recreate script for %s: %s", service.name, e)
                        continue

                logger.info("Starting service: %s", service.name)
                result = push_service_manager.start_push_service(service.name)
                if result.get("success"):
                    logger.info("Started %s", service.name)
                    service.status = "active"
                    db.session.commit()
                else:
                    logger.error("Failed to start %s: %s", service.name, result.get("message"))

                time.sleep(2)

            logger.info("All push services processed")

        except Exception as e:
            logger.error("Error starting services: %s", e, exc_info=True)

if __name__ == "__main__":
    logger.info("Waiting 10 seconds for system to fully boot...")
    time.sleep(10)
    start_all_services()
