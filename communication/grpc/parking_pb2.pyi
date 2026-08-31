from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Iterable as _Iterable, Mapping as _Mapping, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

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
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

class HeartbeatRequest(_message.Message):
    __slots__ = ("node_id",)
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    node_id: str
    def __init__(self, node_id: _Optional[str] = ...) -> None: ...

class HeartbeatResponse(_message.Message):
    __slots__ = ("acknowledged", "server_time")
    ACKNOWLEDGED_FIELD_NUMBER: _ClassVar[int]
    SERVER_TIME_FIELD_NUMBER: _ClassVar[int]
    acknowledged: bool
    server_time: str
    def __init__(self, acknowledged: bool = ..., server_time: _Optional[str] = ...) -> None: ...

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
    def __init__(self, success: bool = ..., slot_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

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
    def __init__(self, success: bool = ..., message: _Optional[str] = ..., slot_id: _Optional[str] = ...) -> None: ...

class FindParkingRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class FindParkingResponse(_message.Message):
    __slots__ = ("success", "zone_id", "node_id", "slot_id", "reservation_id", "message")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ZONE_ID_FIELD_NUMBER: _ClassVar[int]
    NODE_ID_FIELD_NUMBER: _ClassVar[int]
    SLOT_ID_FIELD_NUMBER: _ClassVar[int]
    RESERVATION_ID_FIELD_NUMBER: _ClassVar[int]
    MESSAGE_FIELD_NUMBER: _ClassVar[int]
    success: bool
    zone_id: str
    node_id: str
    slot_id: str
    reservation_id: str
    message: str
    def __init__(self, success: bool = ..., zone_id: _Optional[str] = ..., node_id: _Optional[str] = ..., slot_id: _Optional[str] = ..., reservation_id: _Optional[str] = ..., message: _Optional[str] = ...) -> None: ...

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
    def __init__(self, success: bool = ..., message: _Optional[str] = ...) -> None: ...

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
    __slots__ = ("nodes",)
    NODES_FIELD_NUMBER: _ClassVar[int]
    nodes: _containers.RepeatedCompositeFieldContainer[NodeInfo]
    def __init__(self, nodes: _Optional[_Iterable[_Union[NodeInfo, _Mapping]]] = ...) -> None: ...

class SetFailureModeRequest(_message.Message):
    __slots__ = ("simulate_failure",)
    SIMULATE_FAILURE_FIELD_NUMBER: _ClassVar[int]
    simulate_failure: bool
    def __init__(self, simulate_failure: bool = ...) -> None: ...

class SetFailureModeResponse(_message.Message):
    __slots__ = ("success", "status")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    STATUS_FIELD_NUMBER: _ClassVar[int]
    success: bool
    status: str
    def __init__(self, success: bool = ..., status: _Optional[str] = ...) -> None: ...
