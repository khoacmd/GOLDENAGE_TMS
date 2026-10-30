-- Profile xe máy cho Việt Nam, dựa trên profile car.lua có sẵn trong image OSRM:
--  * không đi đường cao tốc (motorway) - xe máy bị cấm;
--  * được đi ngõ/đường nhỏ (track, path có cho xe máy) mà ô tô không vào được;
--  * tốc độ tối đa 50 km/h (nội đô).
package.path = '/opt/?.lua;' .. package.path

local car = require('car')
local car_setup = car.setup

local MAX_KMH = 50

function car.setup()
  local profile = car_setup()
  profile.avoid.motorway = true
  profile.avoid.motorway_link = true
  local highway = profile.speeds.highway
  highway.track = 15
  highway.path = 12
  for key, speed in pairs(highway) do
    highway[key] = math.min(speed, MAX_KMH)
  end
  profile.access_tags_hierarchy = Sequence { 'motorcycle', 'motor_vehicle', 'vehicle', 'access' }
  profile.default_speed = 15
  return profile
end

return car
