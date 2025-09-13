#!/usr/bin/env python3
"""
MetaGPSD - GPS attachment service for Kismet remote capture
Connects to GPSd and forwards GPS data to Kismet via websocket
"""

import argparse
import asyncio
import json
import signal
import sys
import threading
import websockets

from gpsdclient import GPSDClient
from loguru import logger


class MetaGPSD:
    def __init__(self, host_uri, name, apikey, use_ssl=False):
        self.endpoint_uri = f"{'wss' if use_ssl else 'ws'}://{host_uri}/gps/meta/{name}/update.ws?KISMET={apikey}"
        self.exit_event = threading.Event()  # Event used for clean exit
        self.gpsdclient = None
        signal.signal(signal.SIGINT, self.handle_signal)
        signal.signal(signal.SIGTERM, self.handle_signal)

    def handle_signal(self, signum, frame):
        logger.warning(f"Received {signal.Signals(signum).name}")
        self.exit()

    def exit(self):
        self.exit_event.set()

    async def run_forever(self):
        while not self.exit_event.is_set():
            try:
                await self.main()
            except websockets.ConnectionClosed:
                logger.warning("Connection to Kismet closed, retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue
            except ConnectionRefusedError:
                logger.error("Failed to connect; check Kismet is running, or host URI is valid. Retrying in 5 seconds...")
                await asyncio.sleep(5)
                continue
            except websockets.exceptions.InvalidStatusCode as e:
                if e.status_code == 404:
                    logger.error("Kismet failed to find meta GPS name; check name matches the data source's metagps option.")
                elif e.status_code == 401:
                    logger.error("Kismet rejected API key; check key is valid, and has admin or WEBGPS role.")
                else:
                    logger.exception(e)
                await asyncio.sleep(5)
                continue
            except Exception as e:
                logger.exception("Unexpected error occurred in run_forever")
                await asyncio.sleep(5)
                continue
        logger.info("Exiting")

    async def main(self):
        logger.info("Connecting to GPSd")
        with GPSDClient() as self.gpsdclient:
            while not self.exit_event.is_set():
                try:
                    logger.info("Connecting to Kismet")
                    logger.debug(f"URI: {self.endpoint_uri}")
                    async with websockets.connect(self.endpoint_uri) as websocket:
                        logger.info("Sending location updates")
                        while websocket and not self.exit_event.is_set():
                            gpsd_location = await self.get_gps_fix()

                            kismet_location = {
                                "lat": gpsd_location["lat"],
                                "lon": gpsd_location["lon"]
                            }

                            if gpsd_location["mode"] == 3:
                                # Attempt to get altitude from 'alt', 'altHAE', or 'altMSL'
                                alt = (gpsd_location.get("alt") or
                                       gpsd_location.get("altHAE") or
                                       gpsd_location.get("altMSL") or
                                       gpsd_location.get("height") or
                                       gpsd_location.get("elevation"))
                                if alt is not None:
                                    kismet_location["alt"] = alt
                                else:
                                    logger.warning(f"Altitude data is missing even though mode is 3. gpsd_location: {gpsd_location}")
                            else:
                                logger.info(f"GPS mode is {gpsd_location['mode']}, altitude not expected.")

                            if gpsd_location.get("speed", 0) > 0:
                                # Convert speed from meters per second to kilometers per hour
                                kismet_location["spd"] = gpsd_location["speed"] * 3.6

                            logger.debug(f"Sending location: {kismet_location}")

                            await websocket.send(json.dumps(kismet_location))
                            await websocket.recv()

                            await asyncio.sleep(1)
                except (websockets.ConnectionClosed, websockets.exceptions.ConnectionClosedError):
                    logger.warning("Connection to Kismet lost, attempting to reconnect...")
                    await asyncio.sleep(5)
                    continue
                except Exception as e:
                    logger.exception("Unexpected error occurred in main loop")
                    await asyncio.sleep(5)
                    continue

    async def get_gps_fix(self):
        while not self.exit_event.is_set():
            for result in self.gpsdclient.dict_stream(filter=["TPV"]):
                if result["mode"] >= 2:
                    logger.debug(f"Received GPS data: {result}")
                    return result
                break
            logger.info("Waiting for GPS fix...")
            await asyncio.sleep(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    required_args = parser.add_argument_group('required arguments')
    required_args.add_argument("--connect", dest="host_uri", required=True, help="address of kismet server (host:port)")
    required_args.add_argument("--metagps", dest="metagps", required=True, help="should match a data source's metagps option")
    required_args.add_argument("--apikey", dest="apikey", required=True, help="requires admin or WEBGPS (custom) role")
    parser.add_argument("--ssl", dest="use_ssl", action='store_true', help="use secure connection")
    parser.add_argument("--debug", dest="debug", action='store_true', help="enable debug output")

    args = parser.parse_args()

    if not args.debug:
        logger.remove()
        logger.add(sys.stderr, level="INFO")
    else:
        logger.add(sys.stderr, level="DEBUG")

    m = MetaGPSD(host_uri=args.host_uri, name=args.metagps, apikey=args.apikey, use_ssl=args.use_ssl)
    asyncio.run(m.run_forever())