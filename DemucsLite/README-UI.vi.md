# Demucs Lite — Android UI

Giao diện Android native (Java + XML), tông tím lavender, mint và nền tối. Mở **thư mục DemucsLite này** bằng Android Studio, chờ Gradle Sync rồi Run `app`. Bản Android cũ trong `DemucsLite_deploy/android` và ZIP đóng gói cũ đã được xoá; đây là project Android duy nhất được duy trì.

## Luồng sử dụng

1. **Khám phá**: màn bắt đầu, artwork đĩa nhạc, nút tách nhạc và demo offline.
2. **Thêm bài hát**: chọn MP3/WAV/FLAC/M4A từ trình chọn file Android, xem tên/dung lượng, đổi hoặc bỏ file. Giới hạn 50 MB theo cấu hình backend hiện tại.
3. **Phòng tách âm**: phần trăm upload thực, trạng thái hàng đợi/tách âm của API, tiến trình tải track. Giai đoạn AI hiển thị vòng chờ vì API chưa trả phần trăm. Có thể dừng chờ; thao tác này không hủy tác vụ đã chạy trên server.
4. **Mix studio**: waveform đọc từ WAV, nghe/tạm dừng, tua, slider âm lượng từng track, solo (`S`), mute, đặt lại và lưu WAV. Tạm dừng nghe khi app vào nền; công việc tách nhạc vẫn tiếp tục khi tiến trình app còn sống. ViewModel giữ công việc và mức slider khi xoay màn hình.

**Nghe thử bản demo** tạo loop âm thanh tổng hợp 16 giây trên thiết bị, không cần server. Demo không mô phỏng chất lượng của mô hình tách giọng.

## Kết nối backend

Trên máy Mac hiện tại, backend và môi trường Python đã có sẵn. Chạy `./start-backend.command` từ thư mục DemucsLite (hoặc mở file đó trong Finder) và giữ cửa sổ server mở. Script dùng model thật trong `DemucsLite_deploy/backend`, phục vụ emulator ở cổng 8000. Khi đã chạy, `http://127.0.0.1:8000/health` trên máy tính phải trả `status: ok` và `ready: true`.

Nếu app báo chưa kết nối được: kiểm tra server đang chạy, sau đó kiểm tra địa chỉ trong app. Chỉ mở Android Studio/Run app sẽ không tự bật Python backend.

MP3/M4A và file khác tần số 44.1 kHz cần FFmpeg để giải mã/resample. Backend ưu tiên `FFMPEG_BINARY`, tiếp đến FFmpeg trên PATH, rồi bản đi kèm `imageio-ffmpeg` nếu môi trường Python đã có package này. Máy Mac hiện tại dùng bản đi kèm trong `.venv`; không cần build lại APK khi sửa decoder trên server.

Nhấn biểu tượng cài đặt góc trên:

- Android Emulator: `http://10.0.2.2:8000` (mặc định).
- Điện thoại thật: IP LAN máy chạy backend, ví dụ `http://192.168.1.10:8000`; hai thiết bị cần kết nối được với nhau.
- Chỉ nhập địa chỉ gốc. App tự gọi `POST /separate` (multipart `file`), `GET /status/{job_id}` và tải `result_urls` gồm vocals/drums/bass/other.

URL được lưu trong cài đặt của app. Backend vẫn là dự án hiện có ở thư mục cha, không có thay đổi API từ bản giao diện này.

## Xuất kết quả

Từng track hoặc cả 4 track được lưu bằng MediaStore vào **Downloads/DemucsLite**. Không cần cấp quyền truy cập toàn bộ bộ nhớ. Các file là WAV gốc sau tách; slider/solo/mute chỉ thay đổi khi nghe trong app, chưa render bản mix mới.

## Build và kiểm tra

Yêu cầu Android 10 (API 29) trở lên. Dùng SDK/Gradle/JDK theo cấu hình project.

```sh
./gradlew :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
./gradlew :app:connectedDebugAndroidTest
```

APK: `app/build/outputs/apk/debug/app-debug.apk`.

Kiểm tra tự động gồm WAV demo hợp lệ, waveform, file lỗi/hủy; luồng chọn nhạc; demo/phát nhạc/slider/xoay màn hình/xuất WAV; và upload multipart → polling pending/processing/done → tải 4 track với HTTP fixture cục bộ. Fixture không chạy mô hình AI thật.

## Ảnh chụp trên emulator

- [Màn bắt đầu](reports/ui-preview/01-home.png)
- [Chọn nhạc](reports/ui-preview/02-upload.png)
- [Tiến trình tạo demo](reports/ui-preview/03-processing.png)
- [Mix studio](reports/ui-preview/04-mixer.png)
- [Track và xuất WAV](reports/ui-preview/05-mixer-tracks.png)
