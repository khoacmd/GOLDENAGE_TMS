from collections.abc import Mapping
from dataclasses import dataclass, field

type Window = tuple[int, int]  # [từ, đến] giây tính từ 0h ngày giao


@dataclass(frozen=True)
class Matrix:
    """Ma trận khoảng cách (m) và thời gian di chuyển (giây) giữa các địa điểm (theo chỉ số)."""

    distance_m: list[list[int]]
    duration_s: list[list[int]]


@dataclass(frozen=True)
class Depot:
    id: str
    location: int  # chỉ số trong ma trận


@dataclass(frozen=True)
class Vehicle:
    """Xe vật lý; bộ giải nhân thành nhiều "lượt" (xe ảo) theo `max_trips` x số kho."""

    id: str
    profile: str  # khóa của `Problem.matrices` (vd. "car", "motorbike")
    capacity: int  # đơn vị tải (vd. gram)
    cost_per_km: float
    depot_ids: tuple[str, ...]
    max_trips: int = 1
    fixed_cost: int = 0  # chi phí cố định mỗi lượt (giảm số chuyến)
    # Giờ được rời/về từng kho (kho trong vùng hạn chế); không khai báo = cả ca, rỗng = không dùng.
    depot_windows: Mapping[str, tuple[Window, ...]] = field(default_factory=dict)
    # Khóa của `Problem.penalties`: chi phí phạt cộng thêm theo cặp địa điểm (vd. xe máy qua sông).
    penalty: str | None = None


@dataclass(frozen=True)
class Job:
    """Một điểm cần giao (đã gộp các phần đơn cùng điểm giao, cùng nhóm nhiệt độ, cùng kho)."""

    id: str
    location: int
    depot_id: str  # kho xuất đã chọn trước (mỗi chuyến lấy hàng tại 1 kho)
    demand: int
    vehicle_ids: tuple[str, ...]  # xe tương thích (loại hàng, loại xe khách yêu cầu, tải)
    service_s: int = 0
    # Giờ từng xe được đến điểm này (điểm trong vùng hạn chế); không khai báo = cả ca.
    vehicle_windows: Mapping[str, tuple[Window, ...]] = field(default_factory=dict)
    # Chi phí cộng thêm (đồng) khi xe phục vụ điểm này, để ưu tiên xe khác (vd. điểm gần kho
    # ưu tiên xe máy); chỉ tính vào hàm mục tiêu.
    vehicle_costs: Mapping[str, int] = field(default_factory=dict)


@dataclass
class Problem:
    depots: list[Depot]
    vehicles: list[Vehicle]
    jobs: list[Job]
    matrices: Mapping[str, Matrix]
    shift_start_s: int  # giây tính từ 0h ngày giao
    shift_end_s: int
    turnaround_s: int = 0  # thời gian quay đầu tại kho giữa 2 lượt của cùng xe
    time_limit_s: int = 10
    # Phạt khi bỏ 1 điểm; phải lớn hơn mọi chi phí để bộ giải chỉ bỏ khi không xếp được.
    drop_penalty: int = 10**10
    # Chi phí phạt (đồng) giữa các địa điểm theo chỉ số ma trận, chỉ tính vào hàm mục tiêu.
    penalties: Mapping[str, list[list[int]]] = field(default_factory=dict)


@dataclass
class Route:
    vehicle_id: str
    depot_id: str
    trip_seq: int
    job_ids: list[str]
    arrivals_s: list[int]  # giờ đến từng điểm trong `job_ids`
    distance_m: int
    start_s: int
    end_s: int
    load: int
    cost: float


@dataclass
class Solution:
    routes: list[Route] = field(default_factory=list)
    unassigned: list[str] = field(default_factory=list)
    status: str = "OK"

    @property
    def distance_m(self) -> int:
        return sum(r.distance_m for r in self.routes)

    @property
    def cost(self) -> float:
        return sum(r.cost for r in self.routes)
