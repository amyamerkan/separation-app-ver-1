# Music Source Separation API

API tách nguồn âm thanh (vocals/drums/bass/other) dùng mô hình **DemucsLite** đã huấn luyện ở notebook `w5.ipynb`, đóng gói thành dịch vụ FastAPI.

Tải `demucs_lite_best.pth` từ [Releases](https://github.com/amyamerkan/separation-app-ver-1/releases/tag/v1.0.0), đặt vào thư mục `checkpoints/`. Xem `checkpoints/README.md` để kiểm tra SHA-256.

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
uvicorn app.main:app --reload

```

## Android app

Mở thư mục `DemucsLite/` bằng Android Studio. Khi chạy trên điện thoại qua USB, dùng `adb reverse tcp:8000 tcp:8000` để app truy cập backend trên máy tính tại `http://127.0.0.1:8000`.
