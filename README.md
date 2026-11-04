# DemucsLite

Ứng dụng Android tách nhạc thành vocals, drums, bass và other, kèm backend FastAPI và mô hình DemucsLite V2.

## Cấu trúc

```text
DACNTT/
└── DemucsLite/                 ← mở thư mục này bằng Android Studio
    ├── app/                    # Mã nguồn ứng dụng Android
    ├── gradle/                 # Gradle wrapper và cấu hình build
    ├── DemucsLite_deploy/
    │   ├── backend/            # API, môi trường Python và checkpoint hiện tại
    │   └── training/           # Notebook, mã huấn luyện và đánh giá
    ├── Bao_cao/                # Word, Markdown, sơ đồ và dữ liệu báo cáo
    ├── reports/                # Ảnh giao diện và kết quả kiểm tra
    ├── start-backend.command   # Bật backend trên Mac
    └── gradlew                 # Chạy build Android
```

Thư mục `app/` tại gốc là Android; `DemucsLite_deploy/backend/app/` là Python API. Hai thư mục có chức năng khác nhau và đều cần thiết. Không còn tầng thư mục `demus-lite/DemucsLite` lồng nhau. Backend đời đầu và các tệp upload của nó đã được chuyển vào Thùng rác khi dọn cấu trúc ngày 04/11/2026; lịch sử Git được giữ nguyên trong dự án hiện tại.

## Chạy ứng dụng Android

Mở trực tiếp thư mục này bằng Android Studio. App hỗ trợ Android 10 (API 29) trở lên.

```bash
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

APK: `app/build/outputs/apk/debug/app-debug.apk`. Xem [hướng dẫn giao diện và kết nối API](README-UI.vi.md).

## Backend và mô hình

Chạy `start-backend.command` trên Mac, hoặc làm theo [hướng dẫn triển khai](DemucsLite_deploy/README.vi.md). Checkpoint hiện tại: `DemucsLite_deploy/backend/checkpoints/best_model.pth`.

```bash
cd DemucsLite_deploy/backend
.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Android Emulator dùng `http://10.0.2.2:8000`; điện thoại thật dùng IP LAN của máy chạy backend và đổi URL trong cài đặt app. Notebook huấn luyện nằm trong `DemucsLite_deploy/training/`.

[Bộ báo cáo dự án](Bao_cao/README.md). Build/cache, cấu hình máy cá nhân và dữ liệu upload được loại khỏi Git.
