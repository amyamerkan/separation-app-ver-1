# DemucsLite — gói code, app và model để triển khai

Thư mục này chứa backend đã tích hợp code tách âm mới, notebook Colab và checkpoint đã huấn luyện thực tế. App Android mới nhất nằm ở thư mục cha `DemucsLite`; bản Android đóng gói cũ và file ZIP cũ đã được xoá để tránh dùng nhầm.

## Cấu trúc

```text
DemucsLite_deploy/
├── backend/
│   ├── app/                 FastAPI: upload, status, inference, download
│   ├── audio_sep/           Code model/loss/train/inference mới nhất
│   ├── checkpoints/
│   │   ├── best_model.pth    Checkpoint thật được copy nguyên bản
│   │   └── model_info.json   Epoch, kiến trúc, metric và SHA256
│   ├── tests/               Kiểm tra tích hợp backend
│   ├── Dockerfile
│   └── requirements.txt
├── training/                Notebook Colab tự chứa code, tests và tài liệu
├── compose.yaml
├── .env.example
└── verification.json        Kết quả kiểm tra gói
```

## Model được đưa vào gói

`backend/checkpoints/best_model.pth` là bản **copy byte-for-byte** của file `best_model.pth` người dùng tải từ Colab, được cài vào ngày **10/10/2026**: **DemucsLite V2, epoch 100, trọng số EMA**, 10.309.704 tham số. File có dung lượng 41.307.935 byte (khoảng 39,39 MiB), là bản export để suy luận và không chứa optimizer.

Checkpoint ghi **validation SNR 3,539065 dB**, được chọn tốt nhất trong run `v2_run_01`. Đây không phải điểm test hay BSS Eval SDR chính thức. Chưa chạy lại benchmark chung với model cũ trong lần cài này, nên chưa kết luận mức cải thiện chất lượng giữa hai model.

Backend tự đọc metadata để dựng đúng kiến trúc V2. Ngày 10/10/2026, các checkpoint cũ và repo `separation-app-ver-1` được chuyển vào Thùng rác theo yêu cầu người dùng; GitHub giữ nguyên. Bản code huấn luyện được giữ tại `training/`; bản trùng trong `separation_lab` đã được dọn. Nhật ký đường dẫn nằm trong `../reports/local_cleanup_2026_10_10.json` trên máy chuẩn bị gói.

SHA256 của checkpoint:

```text
c8afd78e8f49dfcde538f008345c9bdd64c305d88da9386b50138ebe3b36c5d3
```

## Chạy backend bằng Python

Cần Python 3.12 và FFmpeg trên PATH. FFmpeg giúp đọc MP3/M4A khi SoundFile không đọc trực tiếp được. Chạy từ `backend`:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
```

Trên Windows kích hoạt bằng `.venv\Scripts\activate`. Endpoint kiểm tra: `http://localhost:8000/health`; API docs: `http://localhost:8000/docs`.

Model mặc định ở `backend/checkpoints/best_model.pth`. Biến `CHECKPOINT_PATH` chỉ cần đặt nếu chọn file khác. `MODEL_DEVICE=auto` chọn CUDA khi có; `cpu` ép CPU, `cuda` yêu cầu GPU tương thích. Container mặc định dùng CPU. Để chạy GPU, cần bản PyTorch/CUDA và driver phù hợp trên server; Dockerfile CPU trong gói chưa được dùng để kiểm thử GPU.

API giữ hợp đồng của app Android:

| Request | Kết quả |
|---|---|
| `POST /separate`, multipart field `file` | `job_id`, `status` |
| `GET /status/{job_id}` | `pending` → `processing` → `done` hoặc `failed` |
| `result_urls` khi done | Link `vocals.wav`, `drums.wav`, `bass.wav`, `other.wav` |
| `GET /files/{job_id}/{stem}.wav` | WAV PCM16 để Android phát và tải |

Backend dùng inference theo đoạn chồng lấn thay cho đưa cả bài vào model. Kết quả PCM16 áp dụng **cùng một hệ số giảm peak cho cả bốn stem** nếu cần; không tự tăng/giảm từng stem riêng. Model/loss gốc trong `training` vẫn xuất WAV float để tính metric.

## Chạy backend bằng Docker Compose

Chạy từ thư mục chứa `compose.yaml`:

```bash
cp .env.example .env
docker compose up --build -d
docker compose logs -f api
```

Container đóng gói checkpoint sẵn có, FFmpeg và thư viện cần thiết. Thư mục storage nằm trong volume `separation_storage`, giữ file kết quả khi container khởi động lại. **Chưa build hoặc chạy image tại máy chuẩn bị gói: Docker daemon chưa hoạt động.** Cấu hình Compose được kiểm tra bằng `docker compose config`.

JobStore đang nằm trong bộ nhớ, nên chỉ dùng **một worker** như cấu hình đã cung cấp. Sau khi restart, các file WAV vẫn có trong volume nhưng trạng thái job cũ không được khôi phục; request đang xử lý cần gửi lại. Khi cần nhiều worker hoặc nhiều instance, phải bổ sung queue và kho trạng thái dùng chung.

Với server có domain qua reverse proxy HTTPS, đặt trong `.env`:

```dotenv
PUBLIC_BASE_URL=https://api.example.com
```

Đổi thành domain thật của bạn. Nếu để trống, backend tạo link tải theo host của request upload. Nhờ đó Android emulator dùng `10.0.2.2`, hoặc điện thoại dùng IP LAN, nhận được link cùng host thay vì `localhost` của điện thoại. Lệnh Compose trên chỉ là hướng dẫn; chưa có dịch vụ nào được đưa lên cloud.

Cloud storage S3/GCS vẫn giữ trong code, nhưng image/Compose mặc định dùng local. Muốn dùng S3/GCS trên server, cài thêm `backend/requirements-cloud.txt` và cấu hình bucket/credentials trong môi trường server; gói không chứa credentials.

## Kết nối và build app Android

Mở thư mục cha `DemucsLite` bằng Android Studio. App yêu cầu Android 10 (API 29) trở lên, compile/targetSdk 37. URL mặc định là `http://10.0.2.2:8000` cho emulator. Đổi địa chỉ server trực tiếp trong cài đặt của app khi dùng điện thoại thật hoặc domain HTTPS.

Từ thư mục `DemucsLite`, build và kiểm tra:

```bash
./gradlew clean :app:assembleDebug :app:testDebugUnitTest :app:lintDebug
```

APK mới nằm tại `app/build/outputs/apk/debug/app-debug.apk`. Trên Windows dùng `gradlew.bat`. Xem [hướng dẫn giao diện Android](../README-UI.vi.md) để chạy backend và sử dụng app.

## Train V2 và thay model sau này

Upload `training/main_v2_training_colab.ipynb` vào Google Colab để chỉ train V2. Bản `training/main_improved_colab.ipynb` giữ luồng so sánh cả V2 và HTDemucs. Notebook tự tạo code, audit dữ liệu, train/resume và xuất ngay `best_model.pth` mỗi khi validation cải thiện; file best đã xuất vẫn còn nếu phiên bị ngắt ở epoch sau. Dữ liệu và checkpoint được lưu riêng trên Drive; gói deploy không chứa dataset MUSDB18-HQ 22 GB.

Notebook V2 đã sửa lỗi cell đầu tự chặn Python 3.13: giữ PyTorch/NumPy có sẵn trên Colab, không cài Demucs/torchaudio hoặc ép NumPy xuống 1.x. Bản hiện tại đã qua 36 test Lite trên Python 3.13.7, PyTorch 2.14.0, NumPy 2.2.6 CPU. Upload notebook mới bằng File → Upload notebook, chọn GPU rồi chạy từ đầu; notebook cũ đang mở trên Drive không tự cập nhật theo file local.

Nếu dataset ở **Được chia sẻ với tôi**, thêm shortcut thư mục `musdb18hq` vào MyDrive bằng **Sắp xếp → Thêm lối tắt → MyDrive**. Shortcut giữ file ở Drive của chủ sở hữu, không tạo bản sao ZIP 22 GB trong tài khoản của bạn. Sau khi thêm, remount Drive và chạy lại cell tìm ZIP. Nếu vẫn không thấy ZIP, notebook mới tải bằng tài khoản Google có quyền đọc file trực tiếp xuống ổ tạm `/content` của Colab. Checkpoint do bạn tạo vẫn cần dung lượng lưu riêng trên MyDrive. [Google Drive: file chia sẻ và dung lượng](https://support.google.com/drive/answer/9312312?hl=en), [thêm shortcut](https://support.google.com/drive/answer/2375057?co=GENIE.Platform%3DDesktop&hl=en).

Riêng `test/PR - Oh No`, scanner ghi cảnh báo residual hai kênh và giữ nguyên mixture/stems cùng đủ 50 track test. [SigSep chỉ ghi nhận errata kênh trái](https://sigsep.github.io/datasets/musdb.html#errata); residual kênh phải là quan sát thêm trong dữ liệu của bạn, chưa xác định nguyên nhân. Các track khác cùng kiểm tra metadata/shape/finite vẫn giữ nguyên. Báo cáo có điểm toàn bộ test và điểm phụ bỏ track gắn cờ, không thay mixture để làm đẹp điểm. Nếu phiên Colab đã giải nén, upload `training/colab_fix_dataset_audit_v2.py` rồi chạy `%run -i /content/colab_fix_dataset_audit_v2.py`. Bản sửa cập nhật scanner/evaluation, reload module và tự audit khi có biến `EXTRACT_ROOT`; nếu đủ 86 train/14 val/50 test, chạy tiếp cell Train Lite V2. Không chạy lại cell ghi module của notebook cũ.


Nếu cell Train chỉ hiện `CalledProcessError`, đó là mã thoát của tiến trình con, chưa xác định được nguyên nhân. Bản notebook mới dùng launcher có log: cố định cwd về PROJECT, chạy Python không buffer, gộp stdout/stderr, hiển thị trực tiếp output và lưu từng lần chạy trong PROJECT/logs; log được copy vào run-dir/logs khi Drive ghi được. Nếu train lỗi, thông báo giữ đúng exit code và 50 dòng cuối chứa traceback thật. Không tự đổi AMP, segment hoặc worker để đoán nguyên nhân.

Với phiên Colab đang mở, upload `training/colab_train_with_logs.py`, chạy `%run -i /content/colab_train_with_logs.py`, rồi chạy cell Train hiện tại. Helper không tự train khi nạp. Đừng chạy lại cell cấu hình có hàm train_run cũ sau đó vì nó sẽ ghi đè launcher. Giữ nguyên cấu hình để resume; chỉ chỉnh TRAIN_WORKERS/TRAIN_NO_AMP khi đã xác định lỗi và cấu hình phù hợp. Nếu vẫn dừng, gửi traceback nằm sau dòng “50 dòng cuối của tiến trình train”.


Sửa lỗi `Nonfinite gradients. Retry --no-amp.`: code trước dừng sau kiểm tra norm và trước `GradScaler.step/update`. Trainer mới kiểm tra từng gradient sau unscale; với AMP, gradient không hữu hạn làm GradScaler bỏ bước optimizer và giảm scale, đồng thời giữ nguyên EMA/số step. Norm được tính float64 để phân biệt overflow của tổng norm với gradient thật sự NaN/Inf. Log/history ghi precision, scale và số nhóm bỏ qua; 8 nhóm overflow liên tiếp làm dừng để kiểm tra tiếp, còn FP32 không hữu hạn vẫn dừng. Giới hạn này là guard phục hồi, không phải hyperparameter chất lượng tối ưu đã được chứng minh. [Quy trình AMP chính thức](https://docs.pytorch.org/docs/stable/notes/amp_examples).

Run V2 đã hoàn tất 100 epoch theo người dùng; checkpoint export epoch 100 đã được kiểm tra trực tiếp và đưa vào backend. Khi cần nối một lần train bị gián đoạn, chạy lại với `TRAIN_NO_AMP=True`, giữ nguyên run-dir/manifest/segment/crops/LR, để resume bằng FP32 từ cuối epoch hoàn tất gần nhất. Phần epoch đang dở phải chạy lại. AMP sang FP32 giữ model/optimizer/EMA và bỏ scaler cũ; FP32 sang AMP khởi tạo scaler nếu checkpoint không có trạng thái scaler. Metadata ghi chuyển chế độ. FP32 có thể tốn thêm VRAM/thời gian; không đổi segment trong run đang resume. [PyTorch: lưu và resume AMP](https://docs.pytorch.org/tutorials/recipes/recipes/amp_recipe.html).

Để áp dụng trainer mới vào phiên Colab hiện tại, upload `training/colab_fix_amp_training.py`, chạy `%run -i /content/colab_fix_amp_training.py`, rồi `train_run('lite', LITE_DIR, LITE_EPOCHS, 3e-4, 15)`. Bản vá chỉ thay train.py, giữ backup code trước sửa, cài logger và đặt TRAIN_NO_AMP=True; nó chưa tự bắt đầu train, chưa thay đổi WAV, manifest hoặc checkpoint. Không chạy lại cell ghi module/cấu hình cũ sau bản vá.

Sau khi có checkpoint V2 hoặc HTDemucs fine-tune thật:

1. Giữ lại file model hiện tại để rollback.
2. Đặt checkpoint mới vào `backend/checkpoints/best_model.pth` hoặc dùng `CHECKPOINT_PATH` trỏ tới file mới.
3. Chạy `/health` và tách thử để xác nhận kiến trúc, thứ tự stem và audio.
4. Nếu dùng Docker với checkpoint copy vào image, build lại image rồi khởi động lại service.

Checkpoint V2 phải giữ `format_version`, `model_kind`, `model_config`, thứ tự nguồn và trọng số do `audio_sep.train` xuất. Nạp file từ nguồn bạn tin cậy; loader không tự chuyển checkpoint tensor trần thành một kiến trúc khác.

## Kiểm tra trước khi chuyển gói

Từ `backend`:

```bash
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

Từ `training`:

```bash
python -m unittest discover -s tests -v
```

Tests kiểm tra luồng xử lý và tính đúng của code bằng audio tổng hợp, không đo chất lượng nghe trên MUSDB. `verification.json` lưu kết quả kiểm tra gói trước đây; mục Android trong đó thuộc bản cũ đã xoá. Kiểm tra app hiện tại theo lệnh trong README Android.
