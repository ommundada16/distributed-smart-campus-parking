"""gRPC middleware that carries the Lamport clock on every call (Unit 3:
Lamport's algorithm).

The client interceptor ticks the caller's clock and attaches it as call
metadata; the server interceptor merges it on receipt and returns its own
clock in the trailing metadata, which the client merges when the reply
arrives. Application code never touches the clock for ordinary RPCs - the
middleware does it, which is exactly the role middleware plays in Unit 1.
"""

import collections

import grpc

from distributed import clocks

LAMPORT_KEY = "x-lamport"


class _ClientCallDetails(
    collections.namedtuple("_ClientCallDetails", ("method", "timeout", "metadata", "credentials", "wait_for_ready", "compression")),
    grpc.ClientCallDetails,
):
    pass


class ClientClockInterceptor(grpc.UnaryUnaryClientInterceptor):
    def intercept_unary_unary(self, continuation, client_call_details, request):
        clock = clocks.get_clock()
        if clock is None:
            return continuation(client_call_details, request)

        metadata = list(client_call_details.metadata or [])
        metadata.append((LAMPORT_KEY, str(clock.tick())))
        details = _ClientCallDetails(
            client_call_details.method, client_call_details.timeout, metadata,
            client_call_details.credentials, getattr(client_call_details, "wait_for_ready", None),
            getattr(client_call_details, "compression", None),
        )
        call = continuation(details, request)
        try:
            trailing = dict(call.trailing_metadata() or [])
            if LAMPORT_KEY in trailing:
                clock.update(int(trailing[LAMPORT_KEY]))
        except Exception:
            pass
        return call


class ServerClockInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, handler_call_details):
        handler = continuation(handler_call_details)
        if handler is None or handler.request_streaming or handler.response_streaming or handler.unary_unary is None:
            return handler

        inner = handler.unary_unary

        def wrapper(request, context):
            clock = clocks.get_clock()
            if clock is not None:
                md = dict(context.invocation_metadata())
                if LAMPORT_KEY in md:
                    clock.update(int(md[LAMPORT_KEY]))
            try:
                return inner(request, context)
            finally:
                if clock is not None:
                    try:
                        context.set_trailing_metadata(((LAMPORT_KEY, str(clock.tick())),))
                    except Exception:
                        pass

        return grpc.unary_unary_rpc_method_handler(
            wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
