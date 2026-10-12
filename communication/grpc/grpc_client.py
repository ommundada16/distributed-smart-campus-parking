"""RPC middleware: helpers for building gRPC channels/stubs and servers.

Application code calls these instead of touching grpc.insecure_channel
directly, so the networking mechanics (channel reuse, reconnect back-off,
logical-clock propagation) stay in one place. Channels are cached per target
and wrapped with the clock interceptor.
"""

import threading
from concurrent import futures

import grpc

import config
from communication.grpc import parking_pb2_grpc
from communication.grpc.clock_interceptors import ClientClockInterceptor, ServerClockInterceptor

_channels: dict[str, grpc.Channel] = {}
_lock = threading.Lock()

_CHANNEL_OPTIONS = [
    ("grpc.initial_reconnect_backoff_ms", 200),
    ("grpc.min_reconnect_backoff_ms", 200),
    ("grpc.max_reconnect_backoff_ms", 1500),
]


def get_channel(host: str, port: int) -> grpc.Channel:
    target = f"{host}:{port}"
    with _lock:
        channel = _channels.get(target)
        if channel is None:
            channel = grpc.intercept_channel(
                grpc.insecure_channel(target, options=_CHANNEL_OPTIONS), ClientClockInterceptor()
            )
            _channels[target] = channel
        return channel


def coordinator_stub(host: str, port: int):
    return parking_pb2_grpc.CoordinatorStub(get_channel(host, port))


def zone_stub(host: str, port: int):
    return parking_pb2_grpc.ZoneServiceStub(get_channel(host, port))


def replica_stub(coord_id: int):
    cfg = config.COORDINATORS[coord_id]
    return coordinator_stub(cfg["host"], cfg["port"])


def zone_stub_for(zone_key: str):
    cfg = config.ZONES[zone_key]
    return zone_stub(cfg["host"], cfg["port"])


def make_server(max_workers: int = 16) -> grpc.Server:
    """gRPC server with the clock-propagation interceptor installed."""
    return grpc.server(
        futures.ThreadPoolExecutor(max_workers=max_workers),
        interceptors=[ServerClockInterceptor()],
    )
