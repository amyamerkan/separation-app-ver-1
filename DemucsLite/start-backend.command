#!/bin/zsh
# Run the bundled trained model for the Android emulator.
set -eu
cd -- "${0:A:h}/DemucsLite_deploy/backend"
if curl --silent --fail --max-time 2 http://127.0.0.1:8000/health > /dev/null; then
  printf 'Server đang chạy. Trong app dùng: http://10.0.2.2:8000\n'
  exit 0
fi
if [[ ! -x .venv/bin/python ]]; then
  printf 'Chưa có môi trường Python. Xem DemucsLite_deploy/README.vi.md để cài backend.\n'
  exit 1
fi
printf 'Đang bật model. Giữ cửa sổ này mở khi dùng app.\n'
printf 'Địa chỉ trong Android Emulator: http://10.0.2.2:8000\n'
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --workers 1
