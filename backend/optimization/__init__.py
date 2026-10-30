"""Bộ giải bài toán định tuyến xe (VRP) - thuần Python, không phụ thuộc FastAPI/DB.

Đầu vào/đầu ra là dataclass (xem `model.py`) để test độc lập và có thể tách thành service riêng.
"""

from optimization.model import Depot, Job, Matrix, Problem, Route, Solution, Vehicle
from optimization.vrp import solve

__all__ = ["Depot", "Job", "Matrix", "Problem", "Route", "Solution", "Vehicle", "solve"]
