"""RPC middleware: thin helpers for building gRPC channels/stubs.

Application code calls these instead of touching grpc.insecure_channel
directly, so the networking mechanics stay in one place.
"""

import grpc

from communication.grpc import parking_pb2_grpc


def coordinator_stub(host: str, port: int):
    channel = grpc.insecure_channel(f"{host}:{port}")
    return parking_pb2_grpc.CoordinatorStub(channel)


def zone_stub(host: str, port: int):
    channel = grpc.insecure_channel(f"{host}:{port}")
    return parking_pb2_grpc.ZoneServiceStub(channel)
