# DemucsLite

Ứng dụng Android tách nhạc thành vocals, drums, bass và other, kèm backend FastAPI và model DemucsLite V2 đã huấn luyện.

## App Android mới nhất

Mở **`DemucsLite/`** bằng Android Studio. Đây là project Android duy nhất đang duy trì; bản Android đóng gói cũ đã được xoá.

```bash
cd DemucsLite
./gradlew clean :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

APK: `DemucsLite/app/build/outputs/apk/debug/app-debug.apk`. App hỗ trợ Android 10 (API 29) trở lên. Xem [giao diện, kết nối API và kiểm tra](DemucsLite/README-UI.vi.md).

## Backend và model hiện tại

Backend đang dùng nằm tại `DemucsLite/DemucsLite_deploy/backend`, kèm checkpoint `checkpoints/best_model.pth`. Cài Python và dependencies theo [hướng dẫn triển khai](DemucsLite/DemucsLite_deploy/README.vi.md), sau đó chạy từ thư mục backend:

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Trên Mac đã cài môi trường backend, có thể chạy `DemucsLite/start-backend.command`. Android Emulator dùng `http://10.0.2.2:8000`; điện thoại thật dùng IP LAN của máy chạy backend và đổi URL trong cài đặt app.

Code backend đời đầu tại `app/` và `scripts/` được giữ để tham khảo. Notebook huấn luyện hiện tại nằm trong `DemucsLite/DemucsLite_deploy/training/`.

Build/cache, cấu hình máy cá nhân và dữ liệu upload không đưa vào Git.
