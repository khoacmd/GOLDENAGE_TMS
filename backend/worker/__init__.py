"""Worker tác vụ nền (Dramatiq) và job định kỳ (APScheduler).

Chạy (trong backend/):
  uv run dramatiq worker.tasks --threads 1      # worker
  uv run python -m worker.scheduler             # lịch lập kế hoạch tự động
"""
