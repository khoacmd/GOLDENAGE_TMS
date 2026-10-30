# Dữ liệu mẫu

Bộ dữ liệu demo cho 1 nhà phân phối ở Hà Nội (2 kho, 4 xe, 8 mặt hàng, 8 khách hàng,
8 đơn giao ngày 02/11/2026). Dùng để thử hệ thống và làm ví dụ điền template.

Import theo đúng thứ tự số trong tên file, ở màn hình **Import dữ liệu** trên web
(hoặc `POST /api/v1/imports/{loại}`). Các file dùng header tiếng Việt giống template.

| File | Loại import |
|---|---|
| `1-kho.csv` | Kho hàng (`warehouses`) |
| `2-doi-xe.csv` | Đội xe (`vehicles`) |
| `3-mat-hang.csv` | Mặt hàng (`products`) |
| `4-khach-hang.csv` | Khách hàng & điểm giao (`customers`) |
| `5-ton-kho.csv` | Tồn kho (`inventory`) |
| `6-don-hang.csv` | Đơn hàng (`orders`) |

Tọa độ là vị trí gần đúng trên bản đồ, chỉ dùng cho demo.
