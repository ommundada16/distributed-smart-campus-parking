from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class Empty(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class Ack(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class RegisterNodeRequest(_message.Message):
    __slots__ = ("node_id", "zone_id", "host", "grpc_port", "total_slots")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    HOST_FIELD_NUMBER: _ClassVar[int]
    GRPC_PORT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SLOTS_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    zone_id: str
    host: str
    grpc_port: int
    total_slots: int
    def __init__(self, node_id: _Optional[str] = ..., zone_id: _Optional[str] = ..., host: _Optional[str] = ..., grpc_port: _Optional[int] = ..., total_slots: _Optional[int] = ...) -> None: ...

class RegisterNodeResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    def __init__(self, node_id: _Optional[str] = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("acknowledged", "server_time", "leader_id")
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    SERVER_TIME_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    server_time: str
    leader_id: int
    def __init__(self, acknowledged: _Optional[bool] = ..., server_time: _Optional[str] = ..., leader_id: _Optional[int] = ...) -> None: ...

class ZoneStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class ZoneStatusResponse(_message.Message):
    __slots__ = ("zone_id", "node_id", "total_slots", "available_slots", "occupied_slots", "reserved_slots", "status")
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SLOTS_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_SLOTS_FIELD_NUMBER: _ClassVar[int]
    OCCUPIED_SLOTS_FIELD_NUMBER: _ClassVar[int]
    RESERVED_SLOTS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    zone_id: str
    node_id: str
    total_slots: int
    available_slots: int
    occupied_slots: int
    reserved_slots: int
    status: str
    def __init__(self, zone_id: _Optional[str] = ..., node_id: _Optional[str] = ..., total_slots: _Optional[int] = ..., available_slots: _Optional[int] = ..., occupied_slots: _Optional[int] = ..., reserved_slots: _Optional[int] = ..., status: _Optional[str] = ...) -> None: ...

class AvailableSlotsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class AvailableSlotsResponse(_message.Message):
    __slots__ = ("available_count", "slot_ids")
    AVAILABLE_COUNT_FIELD_NUMBER: _ClassVar[int]
    SLOT_IDS_FIELD_NUMBER: _ClassVar[int]
    available_count: int
    slot_ids: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, available_count: _Optional[int] = ..., slot_ids: _Optional[_Iterable[str]] = ...) -> None: ...

class ReserveSlotRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class ReserveSlotResponse(_message.Message):
    __slots__ = ("success", "slot_id", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    SLOT_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    slot_id: str
    message: str
    def __init__(self, success: _Optional[bool] = ..., slot_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

class ReleaseSlotRequest(_message.Message):
    __slots__ = ("slot_id", "reservation_id")
    SLOT_ID_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    slot_id: str
    reservation_id: str
    def __init__(self, slot_id: _Optional[str] = ..., reservation_id: _Optional[str] = ...) -> None: ...

class ReleaseSlotResponse(_message.Message):
    __slots__ = ("success", "message", "slot_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    SLOT_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    slot_id: str
    def __init__(self, success: _Optional[bool] = ..., message: _Optional[str] = ..., slot_id: _Optional[str] = ...) -> None: ...

class FindParkingRequest(_message.Message):
    __slots__ = ("policy",)
    POLICY_FIELD_NUMBER: _ClassVar[int]
    policy: str
    def __init__(self, policy: _Optional[str] = ...) -> None: ...

class FindParkingResponse(_message.Message):
    __slots__ = ("success", "zone_id", "node_id", "slot_id", "reservation_id", "message", "price_per_hour", "price_source", "policy", "served_by", "lamport")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SLOT_ID_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    PRICE_PER_HOUR_FIELD_NUMBER: _ClassVar[int]
    PRICE_SOURCE_FIELD_NUMBER: _ClassVar[int]
    POLICY_FIELD_NUMBER: _ClassVar[int]
    SERVED_BY_FIELD_NUMBER: _ClassVar[int]
    LAMPORT_FIELD_NUMBER: _ClassVar[int]
    success: bool
    zone_id: str
    node_id: str
    slot_id: str
    reservation_id: str
    message: str
    price_per_hour: float
    price_source: str
    policy: str
    served_by: str
    lamport: int
    def __init__(self, success: _Optional[bool] = ..., zone_id: _Optional[str] = ..., node_id: _Optional[str] = ..., slot_id: _Optional[str] = ..., reservation_id: _Optional[str] = ..., message: _Optional[str] = ..., price_per_hour: _Optional[float] = ..., price_source: _Optional[str] = ..., policy: _Optional[str] = ..., served_by: _Optional[str] = ..., lamport: _Optional[int] = ...) -> None: ...

class ReleaseParkingRequest(_message.Message):
    __slots__ = ("reservation_id",)
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    reservation_id: str
    def __init__(self, reservation_id: _Optional[str] = ...) -> None: ...

class ReleaseParkingResponse(_message.Message):
    __slots__ = ("success", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    def __init__(self, success: _Optional[bool] = ..., message: _Optional[str] = ...) -> None: ...

class SystemStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class NodeInfo(_message.Message):
    __slots__ = ("node_id", "zone_id", "host", "port", "status", "last_heartbeat", "total_slots", "available_slots", "occupied_slots", "reserved_slots")
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    HOST_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    LAST_HEARTBEAT_FIELD_NUMBER: _ClassVar[int]
    TOTAL_SLOTS_FIELD_NUMBER: _ClassVar[int]
    AVAILABLE_SLOTS_FIELD_NUMBER: _ClassVar[int]
    OCCUPIED_SLOTS_FIELD_NUMBER: _ClassVar[int]
    RESERVED_SLOTS_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    zone_id: str
    host: str
    port: int
    status: str
    last_heartbeat: str
    total_slots: int
    available_slots: int
    occupied_slots: int
    reserved_slots: int
    def __init__(self, node_id: _Optional[str] = ..., zone_id: _Optional[str] = ..., host: _Optional[str] = ..., port: _Optional[int] = ..., status: _Optional[str] = ..., last_heartbeat: _Optional[str] = ..., total_slots: _Optional[int] = ..., available_slots: _Optional[int] = ..., occupied_slots: _Optional[int] = ..., reserved_slots: _Optional[int] = ...) -> None: ...

class SystemStatusResponse(_message.Message):
    __slots__ = ("nodes", "leader_id", "term")
    NODES_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[NodeInfo]
    leader_id: int
    term: int
    def __init__(self, nodes: _Optional[_Iterable[_Union[NodeInfo, _Mapping]]] = ..., leader_id: _Optional[int] = ..., term: _Optional[int] = ...) -> None: ...

class SetFailureModeRequest(_message.Message):
    __slots__ = ("simulate_failure",)
    SIMULATE_FAILURE_FIELD_NUMBER: _ClassVar[int]
    simulate_failure: bool
    def __init__(self, simulate_failure: _Optional[bool] = ...) -> None: ...

class SetFailureModeResponse(_message.Message):
    __slots__ = ("success", "status")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    status: str
    def __init__(self, success: _Optional[bool] = ..., status: _Optional[str] = ...) -> None: ...

class ElectionRequest(_message.Message):
    __slots__ = ("from_id",)
    FROM_ID_FIELD_NUMBER: _ClassVar[int]
    from_id: int
    def __init__(self, from_id: _Optional[int] = ...) -> None: ...

class ElectionResponse(_message.Message):
    __slots__ = ("ok", "term")
    OK_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    ok: bool
    term: int
    def __init__(self, ok: _Optional[bool] = ..., term: _Optional[int] = ...) -> None: ...

class AnnounceRequest(_message.Message):
    __slots__ = ("leader_id", "term")
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    leader_id: int
    term: int
    def __init__(self, leader_id: _Optional[int] = ..., term: _Optional[int] = ...) -> None: ...

class AnnounceResponse(_message.Message):
    __slots__ = ("accepted",)
    ACCEPTED_FIELD_NUMBER: _ClassVar[int]
    accepted: bool
    def __init__(self, accepted: _Optional[bool] = ...) -> None: ...

class BeaconRequest(_message.Message):
    __slots__ = ("leader_id", "term")
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    leader_id: int
    term: int
    def __init__(self, leader_id: _Optional[int] = ..., term: _Optional[int] = ...) -> None: ...

class BeaconResponse(_message.Message):
    __slots__ = ("leader_id", "term")
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    leader_id: int
    term: int
    def __init__(self, leader_id: _Optional[int] = ..., term: _Optional[int] = ...) -> None: ...

class LeaderInfo(_message.Message):
    __slots__ = ("self_id", "self_node", "leader_id", "term", "state", "host", "port")
    SELF_ID_FIELD_NUMBER: _ClassVar[int]
    SELF_NODE_FIELD_NUMBER: _ClassVar[int]
    LEADER_ID_FIELD_NUMBER: _ClassVar[int]
    TERM_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    HOST_FIELD_NUMBER: _ClassVar[int]
    PORT_FIELD_NUMBER: _ClassVar[int]
    self_id: int
    self_node: str
    leader_id: int
    term: int
    state: str
    host: str
    port: int
    def __init__(self, self_id: _Optional[int] = ..., self_node: _Optional[str] = ..., leader_id: _Optional[int] = ..., term: _Optional[int] = ..., state: _Optional[str] = ..., host: _Optional[str] = ..., port: _Optional[int] = ...) -> None: ...

class OverflowBookRequest(_message.Message):
    __slots__ = ("use_mutex", "hold_ms", "booking_id")
    USE_MUTEX_FIELD_NUMBER: _ClassVar[int]
    HOLD_MS_FIELD_NUMBER: _ClassVar[int]
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    use_mutex: bool
    hold_ms: int
    booking_id: str
    def __init__(self, use_mutex: _Optional[bool] = ..., hold_ms: _Optional[int] = ..., booking_id: _Optional[str] = ...) -> None: ...

class OverflowBookResponse(_message.Message):
    __slots__ = ("success", "message", "node_id", "saw_free", "request_ts", "entered_at", "exited_at", "trace")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SAW_FREE_FIELD_NUMBER: _ClassVar[int]
    REQUEST_TS_FIELD_NUMBER: _ClassVar[int]
    ENTERED_AT_FIELD_NUMBER: _ClassVar[int]
    EXITED_AT_FIELD_NUMBER: _ClassVar[int]
    TRACE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    message: str
    node_id: str
    saw_free: int
    request_ts: int
    entered_at: float
    exited_at: float
    trace: _containers.RepeatedScalarFieldContainer[str]
    def __init__(self, success: _Optional[bool] = ..., message: _Optional[str] = ..., node_id: _Optional[str] = ..., saw_free: _Optional[int] = ..., request_ts: _Optional[int] = ..., entered_at: _Optional[float] = ..., exited_at: _Optional[float] = ..., trace: _Optional[_Iterable[str]] = ...) -> None: ...

class OverflowReleaseRequest(_message.Message):
    __slots__ = ("booking_id",)
    BOOKING_ID_FIELD_NUMBER: _ClassVar[int]
    booking_id: str
    def __init__(self, booking_id: _Optional[str] = ...) -> None: ...

class RaRequest(_message.Message):
    __slots__ = ("resource", "ts", "from_node")
    RESOURCE_FIELD_NUMBER: _ClassVar[int]
    TS_FIELD_NUMBER: _ClassVar[int]
    FROM_NODE_FIELD_NUMBER: _ClassVar[int]
    resource: str
    ts: int
    from_node: str
    def __init__(self, resource: _Optional[str] = ..., ts: _Optional[int] = ..., from_node: _Optional[str] = ...) -> None: ...

class RaReply(_message.Message):
    __slots__ = ("granted",)
    GRANTED_FIELD_NUMBER: _ClassVar[int]
    granted: bool
    def __init__(self, granted: _Optional[bool] = ...) -> None: ...
