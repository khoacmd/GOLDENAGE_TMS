# Quy định nhà nước ảnh hưởng đến vận hành giao hàng

> Cập nhật: 04/11/2026. **Trạng thái: đã duyệt phương án B, ca đêm để phase sau.** Thiết kế đã thực hiện ở `ARCHITECTURE.md` mục 9c, tiến độ ở `PLAN.md`.
>
> **Cách hiểu đang áp dụng (04/11/2026):** do công ty xác nhận sau khi nghiên cứu lại, xem 1.3. Khác với bản trước: xe tải tính theo **trọng tải hàng**, xe Van tính theo **tổng trọng lượng**.
>
> **Độ tin cậy:** chưa đọc được bản công báo đầy đủ của QĐ 01/2026. Phần còn lại tổng hợp từ bản trích QĐ 52/2026 trên LuatVietnam và báo chí; các chỗ các nguồn khác nhau được ghi ở mục 2. Tài liệu này phục vụ thiết kế, không phải tư vấn pháp lý.

## 1. Quy định đang áp dụng tại Hà Nội

### 1.1 Văn bản

| Văn bản | Ngày | Nội dung liên quan |
|---|---|---|
| QĐ 01/2026/QĐ-UBND | Ban hành 04/01/2026, hiệu lực 15/01/2026 | Thay QĐ 06/2013; mở rộng nội đô đến Vành đai 3,5; quy định giờ hoạt động theo loại xe |
| QĐ 52/2026/QĐ-UBND | Hiệu lực 30/04/2026 | Sửa QĐ 01/2026; xe tải pickup được hoạt động 24/24 |
| Đề án vùng phát thải thấp trong Vành đai 1 | Giai đoạn 1 từ 01/07/2026 | Thí điểm theo lộ trình, xem 1.5 |
| NĐ 168/2024/NĐ-CP, Điều 6 | Đang tra cứu theo bản tổng hợp | Mức phạt, xem 1.6 |

### 1.2 Phạm vi

Áp dụng từ phía trong đường bao vào trung tâm. Theo báo chí, đường bao đi qua:

Phạm Văn Đồng → Cầu Diễn, Hồ Tùng Mậu → Xuân Phương → Đường 70 → đường gom Đại lộ Thăng Long → nút An Khánh → Hoàng Tùng (Vành đai 3,5) → Lê Trọng Tấn → Văn Khê → Phúc La → Cầu Bươu → Phan Trọng Tuệ, Ngọc Hồi → ngã tư Pháp Vân → Vành đai 3 → Nguyễn Văn Linh → cầu vượt nút Trung tâm Long Biên → Lý Sơn → cầu Đông Trù → Trường Sa → Hoàng Sa → Võ Văn Kiệt → cầu Thăng Long → Phạm Văn Đồng.

**Tuyến được đi trong khu vực hạn chế (danh sách theo báo chí):** Nguyễn Văn Cừ, Ngọc Lâm, Ngô Gia Khảm, Bắc Thăng Long - Vực Dê, Phương Trạch, Cổ Linh, Đàm Quang Trung, Huỳnh Tấn Phát, Tam Trinh, Đại lộ Thăng Long (đoạn Phạm Hùng đến nút giao đường 70).

Việc thực thi còn theo biển báo tại hiện trường. Dữ liệu trong hệ thống không thay thế được biển báo.

### 1.3 Giờ được hoạt động trong khu vực

Giờ cao điểm: **06:00–09:00** và **16:00–19:30** hằng ngày, gồm cả cuối tuần.

| Loại xe | Căn cứ tính | Mức | Giờ được hoạt động | Trong ca 07:00–19:00 hiện tại |
|---|---|---|---|---|
| Xe tải | Trọng tải hàng, không gồm trọng lượng xe | ≤ 2.000 kg | Ngoài giờ cao điểm | **09:00–16:00** |
| Xe tải | Trọng tải hàng | > 2.000 kg và ≤ 10.000 kg | 21:00–06:00 hôm sau | **Không có giờ nào** |
| Xe Van | Tổng trọng lượng xe + hàng | < 3.500 kg | Mọi khung giờ | 07:00–19:00 |
| Ô tô tải pickup | | | 24/24 (QĐ 52/2026) | 07:00–19:00 |
| Xe ưu tiên (Điều 27 Luật 36/2024/QH15) | | | 24/24 | 07:00–19:00 |
| Xe máy | | | Các nguồn đã đọc không nêu giới hạn giờ theo QĐ 01/2026 (xem 1.5; không đi được Vành đai 3 trên cao) | 07:00–19:00 |

**Cách tính trong hệ thống**

1. Xác định nhóm xe từ `vehicle_type` và `regulatory_class` (trống = xe tải).
2. Xe tải: so `capacity_kg` với các mức trên. Tổng trọng lượng không ảnh hưởng.
3. Xe Van: so `gross_weight_kg` với 3.500 kg. Dưới mức: không giới hạn giờ, không cần văn bản.
4. Khung giờ của xe = giờ theo mức + giờ trong văn bản chấp thuận còn hạn (mục 1.4).

**Hai trường hợp chưa có trong quy định đã xác nhận, đang xử lý theo hướng an toàn:**

| Trường hợp | Đang xử lý | Lý do |
|---|---|---|
| Xe tải trên 10.000 kg hàng | Chỉ vào khi có văn bản chấp thuận | Các nguồn nêu nhóm này do Sở Xây dựng cấp phép; đội xe hiện không có |
| Xe Van từ 3.500 kg, hoặc chưa khai tổng trọng lượng | Tính như xe tải theo trọng tải hàng | Thiếu dữ liệu không được dẫn đến kế hoạch trái luật |

### 1.4 Chấp thuận ngoài khung giờ

- Theo hướng dẫn của Công an TP (nhận hồ sơ từ 16/03/2026 tại Phòng CSGT, 90 Trần Nhật Duật), xe tải 2 đến dưới 10 tấn không được hoạt động giờ cao điểm, trừ một số trường hợp như nhiệm vụ công ích, **hàng thiết yếu**, bưu chính, y tế hoặc theo chỉ đạo của thành phố.
- Hồ sơ: đơn nêu tuyến và thời gian, đăng ký xe, đăng kiểm, giấy giới thiệu hoặc giấy tờ tùy thân, hợp đồng vận chuyển và giấy tờ chứng minh mục đích.
- Việc chấp thuận gắn với tuyến, khung giờ và mục đích. Xe càng nặng thì tuyến càng hạn chế (chủ yếu từ Vành đai 2 trở ra).
- **Chưa rõ:** thời gian xử lý; thời hạn của văn bản.

### 1.5 Vùng phát thải thấp (trong Vành đai 1)

| Giai đoạn | Phạm vi | Nội dung liên quan đến giao hàng |
|---|---|---|
| 1: 01/07–31/12/2026 | Phường Hoàn Kiếm (vùng 1, 2) | Xe tải dưới 2 tấn: ngoài giờ cao điểm; 2 tấn trở lên: 21:00–06:00. Xe máy xăng: hạn chế 19:00–24:00 thứ 6, 7, CN quanh khu phố đi bộ và chợ đêm |
| 2: năm 2027 | Thêm phường Cửa Nam | **Cấm xe tải trên 3,5 tấn**. Xe máy xăng chạy ứng dụng công nghệ bị cấm |
| 3: 2028–2029 | Toàn bộ trong Vành đai 1 | Xe máy xăng dưới mức khí thải 3 không được vào |

Giai đoạn 3 có thể ảnh hưởng trực tiếp đến xe máy giao hàng. Cần theo dõi nội dung và ngày áp dụng thực tế vì lộ trình này đã đổi nhiều lần.

### 1.6 Mức phạt

Theo bản tổng hợp NĐ 168/2024 của LuatVietnam: đi vào khu vực hoặc đường cấm đối với loại phương tiện đang điều khiển bị phạt **4–6 triệu đồng và trừ 2 điểm** GPLX; gây tai nạn: 20–22 triệu đồng và trừ 10 điểm.

## 2. Điểm còn phải xác minh

| # | Vấn đề | Tình trạng các nguồn | Cách xử lý |
|---|---|---|---|
| 1 | Toàn văn QĐ 01/2026 | Chưa đọc được bản gốc; danh sách đường bao và tuyến được đi lấy từ báo, bản trích có thể thiếu | Lấy bản công báo |
| 2 | Căn cứ tính xe tải và xe Van | Công ty xác nhận như 1.3. Các nguồn tôi đọc được lại ghi khác: bản trích QĐ 52/2026 và báo chí dùng "khối lượng toàn bộ của xe dưới 2 tấn", và không nguồn nào nêu mức 3.500 kg cho xe Van | Hệ thống theo cách hiểu của công ty; đối chiếu bản gốc hoặc xác nhận với Phòng CSGT, vì nếu căn cứ là khối lượng toàn bộ thì xe tải 2.000 kg hàng sẽ chỉ được chạy đêm. Đổi chỉ cần sửa file dữ liệu luật |
| 3 | Ranh giới | Một bài của VnExpress (03/2026) viết "trong Vành đai 3", các nguồn khác viết Vành đai 3,5 | Theo văn bản gốc; tạm dùng Vành đai 3,5 |
| 4 | Xe 2 đến 10 tấn trong ngoài giờ cao điểm | Đa số viết chỉ được chạy 21:00–06:00; một trang bán xe (daehan.vn) hiểu là chỉ cấm giờ cao điểm | Thiết kế theo cách hiểu chặt |
| 5 | Xe đúng 10 tấn | "Trên 10 tấn" và "từ 10 tấn" đều xuất hiện | Theo 1.3: đúng 10.000 kg vẫn chạy đêm; không ảnh hưởng đội xe hiện tại |
| 6 | Tên nhóm xe | QĐ 52 đổi "xe ô tô tải thông dụng" thành "các loại xe ô tô tải" ở khoản 2, nhưng điểm a vẫn dùng cụm cũ | Đối chiếu bản gốc |
| 7 | Văn bản mới hơn | Không tìm thấy văn bản nào sau QĐ 52, nhưng không có nghĩa là chưa có | Kiểm tra lại trước khi triển khai |

**Quyết định của công ty (04/11/2026):** sữa và đồ uống được coi là hàng thiết yếu. Đây là căn cứ khi xin chấp thuận ở 1.4, không phải miễn trừ tự động: xe vẫn cần văn bản, và hệ thống chỉ mở thêm giờ khi văn bản đã được nhập.

## 3. Ảnh hưởng đến vận hành

### 3.1 Đội xe

| Xe | Trọng tải hàng | Phân loại | Giờ vào nội đô trong ca |
|---|---|---|---|
| Xe tải | 2.000 kg | Xe tải ≤ 2.000 kg (đúng mức) | **09:00–16:00** |
| Xe Van | 945 kg | Xe Van; cần khai tổng trọng lượng, dưới 3.500 kg thì không giới hạn | 07:00–19:00 |
| Xe máy ×2 | 250 kg | Không giới hạn theo 1.3 | 07:00–19:00 |

Hệ quả so với cách hiểu trước:

- Không còn tình huống cả 2 ô tô đều không vào được nội đô suốt ca.
- **Xe tải chỉ có 7 tiếng trong vùng** và phải rời vùng trước 16:00. Lượt chiều 16:00–19:00 chỉ dùng được cho khách ngoài vùng.
- Xe tải 2.000 kg nằm **đúng mức**: nếu đăng ký chỉ cần cao hơn 2.000 kg, xe chuyển sang chỉ chạy đêm. Phải lấy đúng số trên đăng kiểm.
- Xe Van trở thành xe chính cho nội đô cả ngày, nên phải khai `Xe Van` và tổng trọng lượng khi upload.

Số liệu trên dữ liệu mẫu, ngày 02/11, 12 phần đơn (1 phần đơn thiếu tồn kho ở mọi tình huống):

| Tình huống | Phần đơn xếp được | Chuyến | Km | Vi phạm khi kiểm tra lại |
|---|---|---|---|---|
| Tắt quy định | 11 | 3 | 73 | 0 |
| Bật: xe tải 2.000 kg, xe Van 2.400 kg tổng | 11 | 3 | 71 | 0 |
| Bật: xe tải 2.500 kg (chỉ chạy đêm) | 11 | 5 | 101 | 0 |

Dữ liệu mẫu nhỏ nên chưa thấy ảnh hưởng của khung 09:00–16:00; đo lại khi có dữ liệu thật.

### 3.2 Kho

Dữ liệu mẫu có kho ở Hà Đông và Nguyễn Văn Linh (Long Biên), đều nằm trong ranh giới nháp. Kho **nằm trong** vùng thì xe tải cũng phải rời và về kho trong giờ được phép, kể cả khi giao cho khách ở ngoài vùng: xe ≤ 2.000 kg chỉ rời kho từ 09:00, xe trên 2.000 kg không rời được trong ca. Cần kiểm tra vị trí của kho thật.

### 3.3 Khoảng trống trong hệ thống hiện tại

| Cấu phần | Hiện trạng | Vấn đề |
|---|---|---|
| Xe (`vehicles`) | Chỉ có `capacity_kg`, `vehicle_type` | Thiếu tổng trọng lượng, không phân biệt xe tải, xe Van và pickup |
| Điểm giao, kho | Có tọa độ | Không biết điểm có nằm trong vùng hạn chế không |
| Bộ giải (`optimization/vrp.py`) | Một khung giờ `shift_start`–`shift_end` cho mọi điểm và mọi xe | Không có khung giờ theo cặp xe và điểm |
| Giờ xuất phát | `AddVariableMinimizedByFinalizer` đưa giờ xuất phát về sớm nhất | Xe có thể rời kho lúc 07:00 rồi chờ đến 09:00, có khả năng đứng trong vùng |
| Ma trận và tuyến OSRM | Hồ sơ `car` | Tuyến có thể xuyên nội đô dù cả hai đầu ở ngoài vùng |
| Chia kho (`allocate_warehouses`, `_compatible`) | Theo loại hàng, loại xe, tải | Có thể chọn kho mà chỉ có xe không được phép vào điểm giao |
| Lập lệnh tay, kéo thả (`validate`, `move_stop`) | Không kiểm tra giờ | `TripIn` không có giờ xuất phát; lệnh tay không có `planned_start` |
| Giờ từng điểm | Chỉ có giờ đầu và cuối chuyến | Không kiểm tra được giờ xe có mặt trong vùng |
| Quy tắc giờ xác nhận (`delivery/service.py`) | Theo ca của `plan_date` | Chuyến đêm qua 0h sẽ bị từ chối xác nhận |
| ETA Zalo (`zalo/eta.py`) | Tính từ lần xác nhận gần nhất | Không biết xe phải chờ khung giờ, ETA có thể sớm hơn thực tế |
| Dẫn đường tài xế | Mở Google Maps | Hệ thống không kiểm soát được tuyến thực tế |
| Giả định D5 | Đại lý nhận hàng trong giờ làm việc | Giao đêm cần khung giờ nhận hàng của từng khách |

## 4. Phương án

| | A. Chỉ cảnh báo | **B. Ràng buộc trong bộ giải (đề xuất)** | C. B + ca đêm |
|---|---|---|---|
| Cách làm | Lập như cũ, kiểm tra sau khi có kết quả | Bộ giải chỉ dùng xe và giờ hợp lệ, phần còn lại báo không xếp được kèm lý do | Thêm chuyến 21:00–06:00 và khung giờ nhận hàng của khách |
| Kế hoạch có hợp lệ | Không, quản lý phải sửa tay | Có | Có |
| Năng lực nội đô | Không đổi | Có thể giảm rõ rệt | Dùng lại được xe lớn |
| Thay đổi | Ít | Trung bình | Lớn: lái xe, thủ kho, ca, xác nhận, ETA |
| Phụ thuộc bên ngoài | Không | Dữ liệu vùng và đăng kiểm | Khách đồng ý nhận hàng đêm |

**Đã duyệt: làm B, ca đêm (C) để phase sau.** A vẫn sinh kế hoạch trái luật. C phụ thuộc thỏa thuận với khách nên quyết định sau khi B cho biết có bao nhiêu đơn thực sự không xếp được.

Các quyết định kèm theo: đơn không có xe hợp lệ báo không xếp được, giữ D3; lệnh tay vi phạm chỉ cảnh báo, duyệt phải nhập lý do.

## 5. Thiết kế chi tiết phương án B

> Bản thiết kế lúc xin duyệt, giữ lại để tham khảo; **phần phân loại theo `gross_min_kg`, `gross_max_kg` đã được thay** bằng `weight_basis`, `min_kg`, `max_kg`, `max_inclusive`. Một số chi tiết khác cũng đổi khi làm: không có cột `weekdays`, ngày hiệu lực đặt ở vùng, giờ xuất phát tính lùi sau khi giải. Bản đang dùng: `ARCHITECTURE.md` mục 9c.

### 5.1 Dữ liệu

```
traffic_zones (dùng chung, không RLS, như companies)
  code, name, boundary geography(MultiPolygon), legal_ref, effective_from, effective_to

traffic_zone_rules (dùng chung)
  zone_id, vehicle_class: TRUCK | PICKUP | MOTORBIKE,
  gross_min_kg?, gross_max_kg?,        -- [min, max)
  allowed_windows jsonb,               -- [["09:00","16:00"], ["19:30","06:00"]]; qua 0h được
  weekdays[], effective_from, effective_to, legal_ref

vehicles (thêm)
  gross_weight_kg?                     -- khối lượng toàn bộ theo đăng kiểm
  regulatory_class?: TRUCK | PICKUP    -- ô tô; xe máy suy ra từ vehicle_type

vehicle_permits (theo công ty, có RLS)
  vehicle_id, zone_id, document_no, issuer, valid_from, valid_to, allowed_windows jsonb, note

delivery_points, warehouses (thêm)
  traffic_zone_exempt: bool            -- điểm trên đường bao/tuyến được đi, quản lý xác nhận

company_settings (thêm)
  traffic_rules_enabled: bool          -- mặc định tắt; công ty ở Hà Nội bật
```

- **Luật là dữ liệu có ngày hiệu lực**, không viết cứng trong code: sửa quy định, thêm giai đoạn phát thải thấp hoặc thêm thành phố khác không cần sửa bộ giải. Bộ giải chọn luật theo ngày giao.
- Vùng và luật do công ty vận hành TMS nạp từ file GeoJSON có kiểm soát phiên bản, qua lệnh CLI; chưa cần màn hình quản trị.
- Điểm có nằm trong vùng hay không được tính bằng PostGIS (`ST_Covers`), không lưu sẵn, để đổi ranh giới là có hiệu lực ngay.
- Xe Van chưa khai `gross_weight_kg` được xử lý như xe tải kèm thông báo, để thiếu dữ liệu không dẫn đến kế hoạch trái luật.

Ranh giới cần dựng từ hình học đường trên OSM theo danh sách ở 1.2, rồi người dùng kiểm tra trên bản đồ trước khi nạp.

### 5.2 Lập kế hoạch

Khung giờ của một xe tại một điểm trong vùng = **giờ làm việc ∩ (giờ theo luật ∪ giờ trong văn bản chấp thuận còn hạn)**.

1. **Lọc xe:** `_compatible` loại xe không có khung giờ nào tại điểm đó, nên chia kho cũng không chọn nhầm. Thêm lý do không xếp được, ví dụ: "Điểm giao thuộc vùng hạn chế: các xe phù hợp không được vào trong giờ làm việc".
2. **Khung giờ theo xe trong bộ giải:** áp ràng buộc `xe của điểm ∈ nhóm bị hạn chế ⇒ giờ đến ∈ khung giờ`. Giờ muộn nhất trừ đi thời gian phục vụ và thời gian ra khỏi vùng, vì xe phải rời vùng trước 16:00 chứ không chỉ đến trước 16:00.
3. **Giờ xuất phát:** đổi sang đi muộn nhất có thể để xe không đến sớm rồi chờ trong vùng.
4. **Giờ từng điểm:** `Route` trả thêm giờ đến dự kiến để hiển thị và kiểm tra.
5. **Kho trong vùng:** áp cùng quy tắc cho giờ rời kho và về kho.

### 5.3 Tuyến tránh vùng

- Thêm hồ sơ `car_restricted` cho ô tô bị hạn chế: đoạn đi từ điểm ngoài vùng đến điểm ngoài vùng tính theo tuyến **tránh vùng**; đoạn có một đầu trong vùng tính theo tuyến thường.
- Kỹ thuật dự kiến: dựng OSRM bằng `--location-dependent-data`, gắn class cho đường trong vùng (trừ đường bao và tuyến được đi), rồi gọi `exclude=` khi cần. Cần dựng lại dữ liệu xe ô tô (khoảng 4 GB RAM, 9 GB đĩa).
- Chưa có OSRM hoặc chưa dựng xong: ước lượng như hiện tại và kiểm tra đường thẳng có cắt vùng không để cảnh báo.
- Đổi ranh giới phải dựng lại dữ liệu OSRM.

### 5.4 Lập lệnh tay và kéo thả

- Thêm `planned_start` tùy chọn vào `TripIn`, mặc định là đầu ca.
- Dùng chung hàm kiểm tra mô phỏng lịch chuyến khi đọc, cùng cách với ETA, nên không phải lưu giờ từng điểm và luôn khớp sau khi sửa lệnh.
- Đề xuất **cảnh báo rõ, không chặn**: quản lý còn biết những điều hệ thống không biết (văn bản mới, biển báo, tuyến được đi). Duyệt lệnh còn vi phạm phải nhập lý do và ghi audit.

### 5.5 Giao diện và kênh khác

- **Web:** nhập tổng trọng lượng và phân loại ở trang Đội xe; quản lý văn bản chấp thuận kèm cảnh báo sắp hết hạn; hiện vùng trên bản đồ kế hoạch; đánh dấu điểm giao trong vùng.
- **Import/API:** cột tùy chọn cho xe, cập nhật template và mẫu.
- **Mobile, Zalo tài xế, phiếu giao hàng:** ghi rõ khung giờ được vào vùng của chuyến. Google Maps không biết luật này, nên đây là thông tin nhắc lái xe, không phải kiểm soát.
- **ETA Zalo:** không báo giờ đến trước khung giờ xe được vào vùng.
- **Xác nhận giao:** không từ chối xác nhận vì giờ vào vùng. Hàng đã đến khách thì vẫn phải ghi nhận đúng thực tế.

## 6. Thứ tự thực hiện

| Bước | Nội dung | Điều kiện xong |
|---|---|---|
| 0 | Lấy văn bản gốc, đọc đăng kiểm xe, dựng ranh giới và duyệt trên bản đồ, kiểm tra kho và điểm giao thật | Hết các mục mở ở mục 2, biết tỷ lệ đơn trong vùng |
| 1 | Thử nghiệm kỹ thuật: khung giờ theo xe trên OR-Tools với bộ benchmark 100 điểm; `exclude` trên OSRM | Thời gian giải và số điểm bị bỏ chấp nhận được; nếu không thì đổi cách mô hình |
| 2 | Dữ liệu vùng, luật, xe, văn bản chấp thuận; hiện vùng trên web; cảnh báo ở lệnh tay | Quản lý thấy được vi phạm, chưa đổi kết quả tối ưu |
| 3 | Ràng buộc trong bộ giải, lý do không xếp được, giờ từng điểm | Mọi lệnh tự động qua được bộ kiểm tra lịch độc lập |
| 4 | Tuyến tránh vùng trên production (dựng lại OSRM) | Tuyến xe bị hạn chế không xuyên vùng trong giờ cấm |
| 5 | Mobile, Zalo, phiếu giao, ETA | Lái xe và khách thấy khung giờ đúng |
| Sau | Ca đêm (C), theo kết quả bước 3 | Có thỏa thuận với khách |

**Kết quả bước 1:** mô hình ban đầu với `PATH_CHEAPEST_ARC` trả 0 chuyến khi có vùng; đổi sang `ALL_UNPERFORMED` thì giải được. Trên bộ 100 điểm (5 bộ thử, 15 giây, 31–40 điểm trong vùng): bỏ 1–9 điểm, không vi phạm khung giờ. Chưa xác định phần điểm bị bỏ nào do thiếu năng lực thật, phần nào do bộ giải; tăng lên 60 giây còn bỏ 1–6 điểm. Đo lại khi có dữ liệu thật.

## Nguồn

Văn bản và tin chính thức hoặc báo chí:

- [LuatVietnam: QĐ 52/2026/QĐ-UBND, trích nội dung sửa đổi](https://luatvietnam.vn/giao-thong/quyet-dinh-52-2026-qd-ubnd-ha-noi-sua-doi-bo-sung-quyet-dinh-01-2026-qd-ubnd-ve-giao-thong-duong-bo-433443-d2.html)
- [LuatVietnam: xe bán tải hoạt động cả ngày từ 30/4/2026](https://luatvietnam.vn/tin-van-ban-moi/quyet-dinh-52-2026-qd-ubnd-ha-noi-cho-phep-xe-ban-tai-hoat-dong-ca-ngay-tu-30-4-2026-186-108731-article.html)
- [Báo Xây dựng: cho phép xe bán tải 24/24h](https://baoxaydung.vn/ha-noi-chinh-thuc-cho-phep-xe-ban-tai-luu-thong-24-24h-192260430214839418.htm)
- [Hà Nội Online: chính thức cấm xe tải trong nội đô theo khung giờ](https://hanoionline.vn/ha-noi-chinh-thuc-cam-xe-tai-trong-noi-do-theo-khung-gio-246381620.htm)
- [Vietnamnet: những điều tài xế cần biết](https://vietnamnet.vn/cam-xe-tai-tu-2-tan-vao-ha-noi-ban-ngay-nhung-dieu-tai-xe-can-biet-2482421.html)
- [LSVN: phạm vi và khung giờ hạn chế](https://lsvn.vn/ha-noi-quy-dinh-pham-vi-khung-gio-han-che-phuong-tien-luu-thong-vao-noi-do-a168013.html)
- [LSVN: từ 15/01 cấm xe tải từ 2 tấn ban ngày](https://lsvn.vn/tu-15-01-ha-noi-cam-xe-tai-tu-02-tan-hoat-dong-trong-noi-do-vao-ban-ngay-a168267.html)
- [LSVN: hướng dẫn thủ tục cho xe tải vào khu vực hạn chế](https://lsvn.vn/ha-noi-huong-dan-thu-tuc-cho-xe-tai-xe-hop-dong-vao-khu-vuc-han-che-a170386.html)
- [VnExpress: hầu hết xe bán tải chỉ được vào nội đô 21h-6h (trước QĐ 52, dùng cho cách tính khối lượng)](https://vnexpress.net/hau-het-xe-ban-tai-chi-duoc-vao-noi-do-21h-6h-5053373.html)
- [VTV: lộ trình vùng phát thải thấp](https://vtv.vn/ha-noi-cam-xe-may-xang-khong-dat-chuan-vao-vanh-dai-1-tu-nam-2028-thi-diem-tu-1-7-2026-100260615171236694.htm)
- [Tiền Phong: Đề án vùng phát thải thấp](https://tienphong.vn/ha-noi-xem-xet-thong-qua-de-an-vung-phat-thai-thap-thi-diem-cam-xe-may-xang-theo-gio-tu-17-post1841531.tpo)
- [LuatVietnam: tổng hợp mức phạt NĐ 168 với ô tô](https://luatvietnam.vn/giao-thong/nghi-dinh-168-doi-voi-o-to-863-100626-article.html)

Trang bán xe, chỉ dùng để tham khảo danh sách đường bao:

- [Daehan: Hà Nội cấm xe tải vào nhiều tuyến đường](https://daehan.vn/ha-noi-cam-xe-tai)
