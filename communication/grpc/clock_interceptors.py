"""gRPC middleware that carries logical clocks on every call (Unit 3: Lamport's
and Vector algorithms).

The client interceptor ticks the caller's clocks and attaches them as call
metadata; the server interceptor merges them on receipt and returns its own
clocks in the trailing metadata, which the client merges when the reply
arrives. Application code never touches a clock for ordinary RPCs - the
middleware does it, which is exactly the role middleware plays in Unit 1.
"""

import collections

import grpc

from distributed import clocks

LAMPORT_KEY = "x-lamport"
VCLOCK_KEY = "x-vclock"


class _ClientCallDetails(
    collections.namedtuple("_ClientCallDetails", ("method", "timeout", "metadata", "credentials", "wait_for_ready", "compression")),
    grpc.ClientCallDetails,
):
    pass


class ClientClockInterceptor(grpc.UnaryUnaryClientInterceptor):
    def intercept_unary_unary(self, continuation, client_call_details, request):
        pc = clocks.get_process_clock()
        if pc is None:
            return continuation(client_call_details, request)

        lamport, vc = pc.on_send()
        metadata = list(client_call_details.metadata or [])
        metadata += [(LAMPORT_KEY, str(lamport)), (VCLOCK_KEY, clocks.encode_vc(vc))]
        details = _ClientCallDetails(
            client_call_details.method, client_call_details.timeout, metadata,
            client_call_details.credentials, getattr(client_call_details, "wait_for_ready", None),
            getattr(client_call_details, "compression", None),
        )
        call = continuation(details, request)
        try:
            trailing = dict(call.trailing_metadata() or [])
            if LAMPORT_KEY in trailing:
                pc.on_receive(int(trailing[LAMPORT_KEY]), clocks.decode_vc(trailing.get(VCLOCK_KEY)))
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
            pc = clocks.get_process_clock()
            if pc is not None:
                md = dict(context.invocation_metadata())
                if LAMPORT_KEY in md:
                    pc.on_receive(int(md[LAMPORT_KEY]), clocks.decode_vc(md.get(VCLOCK_KEY)))
            try:
                return inner(request, context)
            finally:
                if pc is not None:
                    try:
                        lamport, vc = pc.on_send()
                        context.set_trailing_metadata(((LAMPORT_KEY, str(lamport)), (VCLOCK_KEY, clocks.encode_vc(vc))))
                    except Exception:
                        pass

        return grpc.unary_unary_rpc_method_handler(
            wrapper,
            request_deserializer=handler.request_deserializer,
            response_serializer=handler.response_serializer,
        )
