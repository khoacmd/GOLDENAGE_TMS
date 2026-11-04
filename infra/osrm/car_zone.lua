-- Profile ô tô có class `trafficzone`: đường trong vùng hạn chế lưu hành. Gọi API kèm
-- `exclude=trafficzone` để tính tuyến tránh vùng; không kèm thì đi như profile car.lua gốc.
-- Vùng lấy từ file GeoJSON truyền cho `osrm-extract --location-dependent-data`, trong đó mỗi vùng có
-- thuộc tính `traffic_zone`. Các tuyến được đi trong vùng theo quy định không gắn class này.
package.path = '/opt/?.lua;' .. package.path

local car = require('car')
local car_setup = car.setup
local car_process_way = car.process_way

-- Tuyến được đi trong khu vực hạn chế (QĐ 01/2026/QĐ-UBND, xem docs/GOV_REGULATION.md 1.2).
local ALLOWED = {
  ['Đường Nguyễn Văn Cừ'] = true, ['Phố Ngọc Lâm'] = true, ['Đường Ngọc Lâm'] = true,
  ['Phố Ngô Gia Khảm'] = true, ['Đường Ngô Gia Khảm'] = true, ['Đường Bắc Thăng Long - Vực Dê'] = true,
  ['Đường Phương Trạch'] = true, ['Đường Cổ Linh'] = true, ['Phố Cổ Linh'] = true,
  ['Đường Đàm Quang Trung'] = true, ['Phố Đàm Quang Trung'] = true, ['Đường Huỳnh Tấn Phát'] = true,
  ['Phố Huỳnh Tấn Phát'] = true, ['Đường Tam Trinh'] = true, ['Phố Tam Trinh'] = true,
  ['Đại lộ Thăng Long'] = true,
}

function car.setup()
  local profile = car_setup()
  profile.classes = Sequence { 'toll', 'motorway', 'ferry', 'restricted', 'tunnel', 'trafficzone' }
  profile.excludable = Sequence {
    Set { 'toll' }, Set { 'motorway' }, Set { 'ferry' }, Set { 'trafficzone' },
  }
  return profile
end

function car.process_way(profile, way, result, relations)
  car_process_way(profile, way, result, relations)
  if way:get_location_tag('traffic_zone') and not ALLOWED[way:get_value_by_key('name') or ''] then
    result.forward_classes['trafficzone'] = true
    result.backward_classes['trafficzone'] = true
  end
end

return car
