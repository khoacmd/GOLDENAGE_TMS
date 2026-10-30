#!/bin/bash
# Gọi adb trong container (dùng adb server của service `adb`).
# Ví dụ: infra/android/adb.sh connect localhost:5555
#        infra/android/adb.sh -s localhost:5555 shell am start -a android.intent.action.VIEW -d exp://172.17.0.1:8081
exec docker run --rm -i --network host tms-adb "$@"
