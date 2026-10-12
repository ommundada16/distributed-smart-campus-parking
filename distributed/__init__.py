"""Pure-Python implementations of the Unit 3 distributed algorithms.

Nothing in this package knows about gRPC, Redis or HTTP. Every algorithm is
written against small injected callables (a "transport"), so it can be unit
tested with an in-memory network and then wired to real gRPC in the services.
"""
