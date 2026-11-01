# Template import dữ liệu

> File sinh tự động từ code (`uv run python -m app.cli export-import-docs ...`), không sửa tay.

## Quy tắc chung

- Định dạng: `.xlsx` (sheet `Dữ liệu` hoặc sheet đầu tiên) hoặc `.csv` UTF-8 (phân cách `,` hoặc `;`). Dòng 1 là header.
- Header dùng **nhãn tiếng Việt** (có/không dấu, dấu `*` được bỏ qua) hoặc **mã cột**; thứ tự cột tùy ý, cột thừa bị bỏ qua.
- Tải template mẫu: `GET /api/v1/imports/templates/{loại}` hoặc màn hình Import trên web.
- **All-or-nothing**: có bất kỳ lỗi nào thì không dòng nào được ghi; kết quả trả về danh sách lỗi theo dòng/cột.
- `dry_run=true`: chỉ kiểm tra, không ghi.
- Mã (kho, hàng, KH...) không phân biệt hoa/thường; mã đã có → cập nhật, chưa có → tạo mới.
- Số: dùng ô số của Excel; với text chấp nhận `12.5` hoặc `12,5`. Ngày: ô ngày của Excel hoặc `dd/mm/yyyy`, `yyyy-mm-dd`. Có/không: `C`/`K`.
- Thứ tự nạp lần đầu: Kho → Đội xe → Mặt hàng → Khách hàng → Tồn kho → Đơn hàng.

## API tích hợp

Hệ thống ngoài gọi `POST /api/v1/integration/{loại}` với header `X-API-Key` (admin công ty tạo key ở màn hình Cấu hình). Body:

```json
{"dry_run": false, "rows": [{"ma_hang": "SUA-TT-180", "ten_hang": "...", ...}]}
```

Key của mỗi dòng là **mã cột** bên dưới; tối đa 5.000 dòng/lần. Kết quả và quy tắc giống import file.

## Kho hàng (`warehouses`)

Mỗi dòng 1 kho. Mã đã tồn tại sẽ được cập nhật.

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Mã kho | `ma_kho` | Có |  | KHO01 |
| Tên kho | `ten_kho` | Có |  | Kho Hà Đông |
| Địa chỉ | `dia_chi` | Có |  | Số 1 Quang Trung, Hà Đông, Hà Nội |
| Vĩ độ | `vi_do` | Có | Latitude, dạng số thập phân | 20.971 |
| Kinh độ | `kinh_do` | Có | Longitude, dạng số thập phân | 105.776 |

## Đội xe (`vehicles`)

Mỗi dòng 1 xe. Mã đã tồn tại sẽ được cập nhật (kể cả danh sách kho).

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Mã xe | `ma_xe` | Có |  | XE01 |
| Tên xe | `ten_xe` | Có |  | Xe tải 2 tấn |
| Biển số | `bien_so` | Có |  | 29C-123.45 |
| Loại xe | `loai_xe` | Có | Ô tô / Xe máy | Ô tô |
| Trọng tải (kg) | `trong_tai_kg` | Có |  | 2000 |
| Chi phí/km (đ) | `chi_phi_km` | Có | Chi phí ước tính mỗi km | 8000 |
| Cần phụ xe | `can_phu_xe` |  | C (có) / K (không), mặc định K | C |
| Loại hàng ưu tiên | `loai_hang_uu_tien` |  | Hàng khô / Đông lạnh / Không phân biệt (mặc định) | Không phân biệt |
| Kho lấy hàng | `kho_lay_hang` | Có | Mã các kho xe được lấy hàng, cách nhau dấu phẩy | KHO01,KHO02 |
| PP ghi nhận chi phí | `pp_chi_phi` |  | Giá trị đơn / Khoảng cách / Khối lượng (mặc định) / Chuyến | Khối lượng |

## Mặt hàng (`products`)

Mỗi dòng 1 mặt hàng. Mã đã tồn tại sẽ được cập nhật.

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Mã hàng | `ma_hang` | Có |  | SUA-TT-180 |
| Tên hàng | `ten_hang` | Có |  | Sữa tươi 180ml (thùng 48 hộp) |
| Loại hàng | `loai_hang` | Có | Khô / Lạnh / Đông | Lạnh |
| Đơn vị tính | `don_vi_tinh` | Có |  | Thùng |
| Trọng lượng (kg) | `trong_luong_kg` | Có | Trọng lượng 1 đơn vị tính, đã gồm bao bì | 9.2 |

## Khách hàng & điểm giao (`customers`)

Mỗi dòng 1 điểm giao; khách hàng nhiều điểm giao thì lặp lại thông tin khách hàng (lấy theo dòng đầu tiên của mã). Điểm giao không có trong file được giữ nguyên.

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Mã KH | `ma_kh` | Có |  | KH001 |
| Tên KH | `ten_kh` | Có |  | Đại lý Minh Anh |
| Địa chỉ KH | `dia_chi_kh` |  |  | 12 Trần Phú, Hà Đông, Hà Nội |
| Người liên hệ | `nguoi_lien_he` |  |  | Nguyễn Văn A |
| Điện thoại | `dien_thoai` |  |  | 0912345678 |
| Email | `email` |  |  | minhanh@example.com |
| Yêu cầu xe | `yeu_cau_xe` |  | Ô tô / Xe máy / Bất kỳ (mặc định) | Bất kỳ |
| NV sales | `nv_sales` |  |  | Trần Thị B |
| Ngày giao | `ngay_giao` |  | Các ngày giao trong tuần: T2..T7, CN | T2,T4,T6 |
| Số lần giao/tuần | `so_lan_giao_tuan` |  |  | 3 |
| Mã điểm giao | `ma_diem_giao` | Có | Duy nhất trong mỗi khách hàng | DG1 |
| Tên điểm giao | `ten_diem_giao` |  |  | Cửa hàng chính |
| Địa chỉ điểm giao | `dia_chi_diem_giao` | Có |  | 12 Trần Phú, Hà Đông, Hà Nội |
| Vĩ độ | `vi_do` | Có |  | 20.9705 |
| Kinh độ | `kinh_do` | Có |  | 105.7782 |
| Điểm mặc định | `diem_mac_dinh` |  | C/K; đơn hàng không ghi điểm giao sẽ giao tới điểm mặc định | C |

## Tồn kho (`inventory`)

Snapshot tồn kho: với mỗi kho xuất hiện trong file, toàn bộ số tồn cũ của kho đó được thay bằng dữ liệu trong file (mặt hàng không có trong file coi như tồn 0).

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Mã kho | `ma_kho` | Có |  | KHO01 |
| Mã hàng | `ma_hang` | Có |  | SUA-TT-180 |
| Số lượng tồn | `so_luong_ton` | Có | Theo đơn vị tính của mặt hàng | 350 |

## Đơn hàng (`orders`)

Mỗi dòng 1 mặt hàng của đơn; các dòng cùng Số đơn được gom thành 1 đơn và phải giống nhau ở thông tin đầu đơn. Đơn đã tồn tại và chưa lập kế hoạch sẽ được thay thế toàn bộ. Đơn tự tách thành phần hàng khô và phần hàng lạnh/đông.

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Số đơn | `so_don` | Có |  | DH2026-0001 |
| Ngày đặt | `ngay_dat` | Có | dd/mm/yyyy | 29/10/2026 |
| Ngày giao yêu cầu | `ngay_giao_yc` | Có | dd/mm/yyyy | 31/10/2026 |
| Mã KH | `ma_kh` | Có |  | KH001 |
| Mã điểm giao | `ma_diem_giao` |  | Bỏ trống = điểm giao mặc định | DG1 |
| Giá trị đơn (đ) | `gia_tri_don` | Có | Tổng giá trị cả đơn | 15600000 |
| Ghi chú | `ghi_chu` |  |  |  |
| Mã hàng | `ma_hang` | Có |  | SUA-TT-180 |
| Số lượng | `so_luong` | Có | Theo đơn vị tính của mặt hàng | 20 |
| Thành tiền (đ) | `thanh_tien` |  | Giá trị dòng hàng (nếu có) | 7800000 |

## Liên hệ khách hàng (`customer_contacts`)

Người liên hệ dùng Zalo Mini App. Để trống mã điểm giao = liên hệ chủ (xem mọi đơn của khách hàng kèm giá trị); có mã điểm giao = chỉ xem đơn đến điểm giao đó (mặt hàng, số lượng). Ghi theo (mã KH, mã điểm giao, điện thoại); liên hệ không có trong file được giữ nguyên.

| Cột | Mã cột | Bắt buộc | Mô tả | Ví dụ |
|---|---|---|---|---|
| Mã KH | `ma_kh` | Có |  | KH001 |
| Mã điểm giao | `ma_diem_giao` |  | Trống = liên hệ chủ của khách hàng | DG1 |
| Tên liên hệ | `ten_lien_he` | Có |  | Nguyễn Văn A |
| Điện thoại | `dien_thoai` | Có | SĐT dùng Zalo; nhận dạng 0912 345 678, +84912345678 | 0912345678 |
| Ghi chú | `ghi_chu` |  |  | Thủ kho đại lý |
| Hoạt động | `hoat_dong` |  | C (mặc định) / K | C |
