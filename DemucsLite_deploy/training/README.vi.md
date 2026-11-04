# Tách nhạc và huấn luyện DemucsLite V2

Bộ code này có hai hướng: dùng HTDemucs đã huấn luyện để nghe kết quả ngay, hoặc huấn luyện DemucsLite V2 để có model riêng cho đồ án. Fine-tune HTDemucs là lựa chọn bổ sung; nó có thể giữ nguyên hoặc làm giảm chất lượng, nên code giữ lại baseline pretrained nếu validation không tốt hơn. Không có checkpoint mới nào được xác nhận tốt hơn model cũ trước khi chạy đánh giá.

Notebook để train V2 trên Colab: **`main_v2_training_colab.ipynb`**, mặc định chỉ train DemucsLite V2, tắt fine-tune HTDemucs và đánh giá full test, rồi nghe checkpoint V2. **`main_improved_colab.ipynb`** giữ luồng so sánh cả hai model. Phân tích notebook cũ nằm trong **`DIAGNOSIS.vi.md`**. Thứ tự stem thống nhất trong toàn bộ code là `vocals, drums, bass, other`.

Notebook V2 dùng PyTorch/NumPy sẵn có của Colab và không chặn Python 3.13 trở lên. Cell đầu chỉ cài NumPy, SoundFile hoặc tqdm khi thiếu hoặc thấp hơn mức tối thiểu; giữ NumPy 2.x đang có, kiểm tra bridge NumPy–PyTorch và GPU. Nó không cài Demucs, torchaudio hoặc pytest. Luồng MUSDB18-HQ đọc WAV 44,1 kHz nên không cần resample; đầu vào khác sample rate của CLI có thể cần torchaudio riêng.

Notebook so sánh giữ môi trường Demucs 4/NumPy 1.26 riêng. Nếu nó báo Python 3.13, khi đã kết nối runtime mở **Command Palette → Change runtime version → 26.07 hoặc 26.04** để dùng Python 3.12. Lựa chọn này không giữ qua phiên mới. Đây là hướng dẫn fallback của [thông báo Colab](https://github.com/googlecolab/colabtools/issues/6081); để chỉ train V2, dùng notebook V2 trên runtime hiện tại.

## Chạy trên Colab

1. Mở Colab, dùng **File → Upload notebook** để mở `main_v2_training_colab.ipynb`; chọn `main_improved_colab.ipynb` nếu muốn chạy thêm fine-tune và so sánh.
2. Chọn GPU trong **Runtime → Change runtime type**. Chạy cell kiểm tra `torch.cuda.is_available()` và thông tin GPU trước khi train; bộ nhớ thực tế quyết định cấu hình phù hợp.
3. Mount Google Drive để lưu checkpoint. Dataset trong Shared with me có thể dùng shortcut đã mount hoặc nhánh tải có xác thực vào `/content`; không cần copy ZIP vào MyDrive.
4. Giải nén dataset vào ổ tạm `/content` để đọc audio nhanh hơn. Quét dataset, kiểm tra audit, chạy kiểm tra code, rồi chạy cell huấn luyện.
5. Mỗi khi validation SNR tốt hơn, code lưu `best.pth` và xuất ngay `best_model.pth` trên Drive để tách thử; bản đã xuất vẫn dùng được nếu epoch sau bị ngắt. Giữ `last.pth` để resume từ epoch hoàn tất gần nhất. Đánh giá full-track sau khi đã khóa cấu hình.

Dataset người dùng cung cấp nằm trong [thư mục Drive](https://drive.google.com/drive/u/0/folders/1l4c8RtXaCe4wy-D3roIQMxnecefKuz1k). Archive có dung lượng khoảng **22,656 GB theo metadata đã đọc**. Máy local chỉ còn khoảng **4,5 GB trống tại thời điểm kiểm tra**, nên không thể chứa archive và phần giải nén trên ổ hiện tại. Runtime Colab/server cũng phải đủ chỗ cho dữ liệu sau giải nén; đừng suy ra dung lượng giải nén từ dung lượng ZIP.

Nếu cell tìm ZIP báo **0 ZIP** vì dataset ở **Shared with me**, bạn có hai cách:

- Trong Drive, chọn folder dùng chung → **Organize → Add shortcut → MyDrive**. Shortcut chỉ trỏ tới folder/file gốc, không tạo bản copy 22 GB. Nếu thêm sau khi mount, chạy `drive.mount('/content/drive', force_remount=True)` rồi chạy lại cell dataset. Đặt `ZIP_PATH` rõ ràng nếu có nhiều ZIP hoặc muốn dùng một đường dẫn cụ thể. [Hướng dẫn shortcut](https://support.google.com/drive/answer/2375057?co=GENIE.Platform%3DDesktop&hl=en)
- Giữ `ZIP_PATH` chưa đặt. Khi tìm thấy 0 ZIP qua mount, notebook dùng đăng nhập Google và Drive API để tải file `1leTZccqRToe17S7DcDXSRsqovnwNaZb5` trực tiếp vào `/content/musdb18hq.zip` của **runtime Colab**. Nó kiểm tra ID/name/size đã xác minh, quyền `canDownload`, dung lượng đĩa và MD5 nếu Drive cung cấp; nếu thiếu MD5, kiểm tra CRC của ZIP. Tải chunk 8 MiB vào `.part`, chỉ đổi thành ZIP hoàn chỉnh sau khi xác minh và dùng lại cache hoàn chỉnh đã kiểm tra. Không tải archive về laptop hoặc ghi vào MyDrive. [Drive API download](https://developers.google.com/workspace/drive/api/guides/manage-downloads)

File trong Shared with me không sử dụng dung lượng file đó trong quota Drive của bạn; tạo shortcut cũng không chép file. MyDrive chỉ cần chỗ cho checkpoint/kết quả nhỏ hơn nhiều. Nhánh tải trực tiếp vẫn cần Colab đủ chỗ cho **ZIP khoảng 21,1 GiB và toàn bộ WAV giải nén**, cộng khoảng trống dự phòng; notebook kiểm tra dung lượng ở cả bước tải và giải nén. File `/content` mất khi runtime bị thu hồi, còn checkpoint lưu trên Drive vẫn còn. Không cần mở chia sẻ công khai hoặc dùng `gdown`. [Quy định dung lượng Drive](https://support.google.com/drive/answer/9312312?hl=en)

**Trạng thái thực thi:** notebook và code được chuẩn bị để chạy. Chống sleep cho hệ thống và màn hình macOS được bật bằng `caffeinate` trong phiên làm việc; cần bật lại nếu ứng dụng hoặc máy khởi động lại. Công cụ vẫn từ chối truy cập Colab vì báo quyền chặn đã lưu, nên chưa gửi được job train, chưa xác nhận GPU và chưa có checkpoint V2 đã huấn luyện. Lỗi Python 3.13 ở cell đầu của bản notebook cũ đã được sửa trong notebook V2 local; phải upload bản cập nhật lên Colab để dùng phần sửa này.

Colab không bảo đảm GPU, thời lượng runtime hoặc khả năng chạy liên tục; lưu checkpoint trên Drive để tránh mất tiến độ. Giữ máy local thức không ngăn Colab thu hồi runtime. [Google Colab FAQ](https://research.google.com/colaboratory/faq.html)

## Chạy trên server hoặc máy có đủ dung lượng

Chạy các lệnh từ thư mục `separation_lab`. Với nhánh Demucs pretrained/so sánh, dùng Python 3.10–3.12 và môi trường riêng:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -c "import torch; print('Torch:', torch.__version__); print('CUDA:', torch.cuda.is_available())"
```

Trên Windows dùng `.venv\Scripts\activate`. Nếu CUDA không khả dụng, kiểm tra bản PyTorch phù hợp với driver/GPU trước khi train; không tự coi CPU là cấu hình tương đương về thời gian chạy.

Nếu chỉ dùng Lite, cài `requirements-lite.txt` thay cho `requirements.txt` trong môi trường PyTorch tương thích với Python/GPU của bạn. File Lite chỉ có torch, NumPy, SoundFile và tqdm, không ép NumPy xuống 1.x hoặc cài stack Demucs. Notebook Lite giữ build PyTorch CUDA có sẵn trên Colab.

Runtime local đã cài để kiểm tra code báo `CUDA=False` và `MPS=False`. Kết quả này mô tả môi trường kiểm tra hiện tại, không chứng nhận GPU trên Colab hoặc toàn bộ khả năng phần cứng của máy. Cùng với dung lượng trống hạn chế, hiện chưa có điều kiện để train/evaluate toàn bộ dataset ngay trên runtime local này.

Layout của MUSDB18-HQ sau giải nén:

```text
musdb18hq/
  train/<tên bài>/mixture.wav, vocals.wav, drums.wav, bass.wav, other.wav
  test/<tên bài>/mixture.wav, vocals.wav, drums.wav, bass.wav, other.wav
```

Quét trước khi huấn luyện:

```bash
python -m audio_sep.data "/path/musdb18hq" --output data/manifest.json
```

Scanner yêu cầu 100 bài trong thư mục train và 50 bài test; 14 bài validation được chọn theo danh sách chính thức, còn 86 bài để train. Nó kiểm tra đủ 5 WAV, stereo 44,1 kHz, số sample bằng nhau, sample hữu hạn trong các probe, và sai số `mixture - sum(stems)` có xét lượng tử hóa WAV. `manifest.audit.json` chứa cảnh báo, lỗi, độ hoạt động từng stem và RMS residual. Ba probe trải đều không chứng nhận toàn bộ bài; mọi crop được loader đọc cũng được kiểm tra hữu hạn. `--no-strict` chỉ nới số lượng bài để phát triển với dataset nhỏ, vẫn kiểm tra audio. [MUSDB18](https://sigsep.github.io/datasets/musdb.html), [danh sách validation chính thức](https://github.com/sigsep/sigsep-mus-db/blob/master/musdb/configs/mus.yaml)

**Track `test/PR - Oh No`:** SigSep ghi nhận mixture kênh trái không bằng tổng stems. Trong dataset của bạn, audit còn đo được residual kênh phải RMS 0,031924/0,021888 ở hai probe. Đây là **additional observed right-channel residual** từ dữ liệu đã quan sát; không phải mô tả errata kênh phải của SigSep. [Errata chính thức cho kênh trái](https://sigsep.github.io/datasets/musdb.html#errata)

Mặc định scanner áp dụng chính sách `warn_known_artistic_mix` cho đúng track test này: residual cả hai kênh trở thành cảnh báo có diagnostics, giữ nguyên mixture/stems và không loại bài khỏi bộ 50 bài test. Tên policy dùng để nhận diện ngoại lệ, không kết luận nguyên nhân mix khác stems. Track khác, cùng tên trong train, sai metadata/shape hoặc sample không hữu hạn vẫn bị từ chối; ngưỡng chung không thay đổi. Không dựng lại mixture benchmark hoặc ghi đè WAV.

Audit ghi `residual_by_channel` cho từng probe, gồm RMS, dB tương đối, peak và ngưỡng warning/failure; provenance phân biệt erratum chính thức bên trái với quan sát thêm bên phải. Manifest ghi `known_issue=musdb18hq_pr_oh_no_left_mixture`, `residual_policy=warn_known_artistic_mix` cùng `max_probe_residual_rms_by_channel`; đây là mức lớn nhất của các probe, không phải kiểm tra mọi sample. Muốn từ chối residual trên cả hai kênh của bài này, dùng `scan_dataset(..., allow_known_errata=False)` hoặc CLI `--reject-known-errata`. `strict=True` vẫn kiểm tra đủ 100 train/50 test như trước. Báo cáo điểm chính giữ toàn bộ test trên mixture/stems gốc, kèm summary phụ bỏ các track đã gắn cờ để thấy ảnh hưởng của mismatch; summary phụ không thay thế kết quả bộ đầy đủ.

## Nghe baseline pretrained trước

```bash
python -m audio_sep.inference "/path/song.wav" \
  --official htdemucs_ft --device cuda \
  --shifts 2 --overlap 0.5 --segment 7.8 \
  --output outputs/htdemucs_ft
```

`htdemucs_ft` là baseline chất lượng mạnh trong các model Demucs được cung cấp, với thời gian tách lớn hơn `htdemucs`; tài liệu chính thức mô tả khoảng 4 lần. Có thể chuyển sang `--official htdemucs` hoặc giảm `--shifts` để thử nhanh hơn. HTDemucs hỗ trợ segment tối đa 7,8 giây. Nếu thiếu VRAM, giảm segment; CPU dùng `--device cpu` và sẽ chậm hơn. Đây là khuyến nghị baseline, không phải lời hứa model tốt nhất cho mọi bài. [Tài liệu Demucs](https://github.com/facebookresearch/demucs#separating-tracks)

Đầu vào CLI này nên là WAV/FLAC mà SoundFile đọc được. MP3/M4A có thể cần chuyển bằng FFmpeg sang WAV trước. Đầu ra là bốn WAV stereo float32 để giữ mức âm lượng và tránh clipping âm thầm; kiểm tra player hỗ trợ WAV float nếu nghe trực tiếp.

## Huấn luyện model riêng

DemucsLite V2 từ đầu:

```bash
python -m audio_sep.train \
  --manifest data/manifest.json --run-dir runs/lite_v2 \
  --kind lite --epochs 100 --segment 6 \
  --train-crops 32 --val-crops 8 \
  --batch-size 1 --accumulate 4 --lr 3e-4 --device cuda
```

Cấu hình này tạo 86 × 32 = **2.752 crop train/epoch**, với vị trí crop thay đổi qua các epoch. Batch vật lý 1 giảm VRAM; tích lũy 4 batch tạo một bước optimizer tương đương tổng hợp 4 crop về gradient. Nó không làm giảm chi phí của một forward 6 giây hoặc tạo batch thống kê thực sự bằng 4. Có thể giảm `--segment` nếu OOM và bắt đầu run mới với cấu hình mới.

Fine-tune **một model `htdemucs`**, không phải cả ensemble `htdemucs_ft`:

```bash
python -m audio_sep.train \
  --manifest data/manifest.json --run-dir runs/htdemucs_finetune \
  --kind pretrained --epochs 100 --segment 6 \
  --train-crops 32 --val-crops 8 \
  --batch-size 1 --accumulate 4 --lr 1e-5 --device cuda
```

Nhánh này đánh giá baseline ở epoch 0 trước khi cập nhật trọng số. Fine-tuning cùng dataset không bảo đảm vượt pretrained; baseline vẫn là best nếu các epoch sau không cải thiện validation SNR. Pretrained đã được huấn luyện trên MUSDB và dữ liệu bổ sung, nên phải ghi rõ dữ liệu mà trọng số nền đã tiếp xúc khi viết báo cáo. [Model pretrained Demucs](https://github.com/facebookresearch/demucs#separating-tracks)

Trong cả hai nhánh, code so sánh trọng số raw và EMA trên validation, chọn theo **SNR validation trung bình từng bài/từng source**, giảm LR khi metric ngừng tăng và early stopping. Mỗi khi có best mới, `best_model.pth` được xuất ngay sau `best.pth`; baseline pretrained ở epoch 0 cũng được xuất trước khi train. `history.csv` ghi SNR/SI-SDR từng stem, tỷ lệ crop active và loss. Checkpoint chỉ lưu sau epoch hoàn tất, nên phần epoch đang chạy có thể mất nếu runtime ngắt. Các hệ số loss là điểm khởi đầu, không phải kết quả tìm kiếm tối ưu đã được chứng minh.

Các file của mỗi run:

| File | Vai trò |
|---|---|
| `last.pth` | Resume: model, optimizer, scheduler, AMP, EMA, RNG và lịch sử |
| `best.pth` | Checkpoint đầy đủ có validation SNR tốt nhất |
| `best_model.pth` | Xuất ngay mỗi khi best thay đổi; chọn đúng raw/EMA, dùng cho inference |
| `history.csv`, `config.json` | Metric và cấu hình để truy vết |

Resume bằng cùng lệnh train, cùng manifest/cấu hình, thêm `--resume`; chỉ tăng số epoch nếu muốn chạy tiếp. Sau khi Colab giải nén lại tại cùng đường dẫn, quét lại dataset để cập nhật manifest. Checkpoint cũ của `DemucsLite` không nạp trực tiếp được vào V2 vì kiến trúc khác.

## So sánh công bằng và kiểm tra code

Cell tìm/tải dataset đã qua **8 kiểm tra offline** bằng ZIP nhỏ và API Google giả lập: đường dẫn explicit, shortcut đã mount, tải trực tiếp vào ổ Colab, tái sử dụng ZIP đã xác minh, nhiều ZIP, thiếu quyền tải, thiếu dung lượng và checksum sai. Chạy lại bằng `python check_dataset_cell.py`. Kiểm tra này không tải ZIP 22 GB thật hoặc xác nhận đăng nhập Google trong runtime Colab.

Đánh giá sau khi cố định cấu hình trên **50 bài test**:

```bash
python -m audio_sep.evaluate --manifest data/manifest.json \
  --official htdemucs_ft --subset test --device cuda --output reports/official_test.json

python -m audio_sep.evaluate --manifest data/manifest.json \
  --checkpoint runs/lite_v2/best_model.pth --subset test --device cuda --output reports/lite_test.json

python -m audio_sep.evaluate --manifest data/manifest.json \
  --legacy-checkpoint "/path/demucs_lite_best_sdr.pth" \
  --subset test --device cuda --output reports/original_test.json
```

`--limit 1` phù hợp để kiểm tra pipeline, không đủ kết luận chất lượng. Evaluator tách full-track bằng cửa sổ overlap, tính median metric trên cửa sổ 1 giây active của từng bài, rồi lấy trung bình các bài và bốn stem. **`snr_db` là SNR phụ thuộc mức âm lượng; `si_sdr_db` là SI-SDR; cả hai không phải BSS Eval SDR dùng trong các benchmark MUSDB.** Không so trực tiếp con số này với SDR công bố trong paper. [Phân tích định nghĩa SDR/SI-SDR](https://arxiv.org/abs/1811.02508)

Model cũ dùng split ngẫu nhiên có thể đã train trên một số bài trong 14 validation chính thức. Vì vậy so sánh old/V2 trên validation mới có thể thiên lệch; dùng test chung và giữ test ngoài quá trình chọn model. Khi so pretrained, ghi rõ lợi thế dữ liệu/pretraining thay vì xem đó là ablation thuần của kiến trúc.

Chạy test từ `separation_lab`:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

**Kiểm tra legacy trước cập nhật errata: 26 test đã pass** trong runtime local với PyTorch 2.5.1 CPU và SoundFile 0.14.0. Kiểm tra gồm alignment/split/remix/stereo, metric/loss, forward/backward thật của một HTDemucs cấu hình giảm, checkpoint offline, pipeline Lite train 1 epoch → resume tới epoch 2 → xuất best → đánh giá full-track bằng audio tổng hợp, và hai tình huống ngắt phiên vẫn giữ đúng export của epoch best/baseline pretrained. Bộ đầy đủ hiện có 38 test sau khi thêm bốn test data/errata, ba test báo cáo và năm test optimizer/AMP; chưa xác nhận lại cả 38 trong môi trường legacy. Các CLI parser được chạy trong cùng process để phù hợp môi trường kiểm tra; không dùng trọng số HTDemucs chính thức tải về hoặc dataset thật để đánh giá chất lượng. Chưa có benchmark xác nhận model mới tách âm tốt hơn model cũ.

Notebook V2 hiện chạy **36 test cho Lite**: toàn bộ test data, inference, model/loss và báo cáo, thêm năm test optimizer/AMP, pipeline train/resume/evaluate và export best khi ngắt phiên. Nó bỏ hai test HTDemucs. **36/36 test đã pass** trên Python 3.13.7, PyTorch 2.14.0, NumPy 2.2.6, SoundFile 0.14.0 CPU. Test data giữ audio gốc, kiểm tra cả hai mức residual phải đã quan sát, strict mode vẫn từ chối cả hai kênh, và ngoại lệ không lan sang track khác/train hoặc bỏ qua nonfinite/sai metadata. Test báo cáo phân biệt kết quả full test và summary phụ bỏ track gắn cờ. Kết quả CPU này không thay thế kiểm tra GPU Colab hoặc đánh giá chất lượng trên dataset thật.

Nếu Colab đã giải nén dataset và đang dừng ở lỗi audit của `PR - Oh No`, upload **`colab_fix_dataset_audit_v2.py`** vào bảng Files của Colab rồi chạy `%run -i /content/colab_fix_dataset_audit_v2.py`. File cập nhật scanner và báo cáo evaluation, lưu bản code trước sửa, reload module trong kernel hiện tại và tự audit nếu `EXTRACT_ROOT` đã được khai báo. Khi hiện đủ **86 train / 14 val / 50 test**, chạy tiếp cell **Train Lite V2**. Không chạy lại cell ghi module từ notebook cũ vì nó sẽ ghi đè bản sửa. Dữ liệu đã giải nén được dùng tiếp; chỉ code và JSON manifest/audit được cập nhật. File tên cũ `colab_fix_dataset_audit.py` trong gói mới cũng chứa bản sửa V2.


Nếu cell Train chỉ hiện `CalledProcessError`, đó là mã thoát của tiến trình con, chưa xác định được nguyên nhân. Bản notebook mới dùng launcher có log: cố định cwd về PROJECT, chạy Python không buffer, gộp stdout/stderr, hiển thị trực tiếp output và lưu từng lần chạy trong PROJECT/logs; log được copy vào run-dir/logs khi Drive ghi được. Nếu train lỗi, thông báo giữ đúng exit code và 50 dòng cuối chứa traceback thật. Không tự đổi AMP, segment hoặc worker để đoán nguyên nhân.

Với phiên Colab đang mở, upload `colab_train_with_logs.py`, chạy `%run -i /content/colab_train_with_logs.py`, rồi chạy cell Train hiện tại. Helper không tự train khi nạp. Đừng chạy lại cell cấu hình có hàm train_run cũ sau đó vì nó sẽ ghi đè launcher. Giữ nguyên cấu hình để resume; chỉ chỉnh TRAIN_WORKERS/TRAIN_NO_AMP khi đã xác định lỗi và cấu hình phù hợp. Nếu vẫn dừng, gửi traceback nằm sau dòng “50 dòng cuối của tiến trình train”.


Sửa lỗi `Nonfinite gradients. Retry --no-amp.`: code trước dừng sau kiểm tra norm và trước `GradScaler.step/update`. Trainer mới kiểm tra từng gradient sau unscale; với AMP, gradient không hữu hạn làm GradScaler bỏ bước optimizer và giảm scale, đồng thời giữ nguyên EMA/số step. Norm được tính float64 để phân biệt overflow của tổng norm với gradient thật sự NaN/Inf. Log/history ghi precision, scale và số nhóm bỏ qua; 8 nhóm overflow liên tiếp làm dừng để kiểm tra tiếp, còn FP32 không hữu hạn vẫn dừng. Giới hạn này là guard phục hồi, không phải hyperparameter chất lượng tối ưu đã được chứng minh. [Quy trình AMP chính thức](https://docs.pytorch.org/docs/stable/notes/amp_examples).

Run của bạn đã train tới epoch 4 rồi dừng. Có thể chạy lại với `TRAIN_NO_AMP=True`, giữ nguyên run-dir/manifest/segment/crops/LR, để resume bằng FP32 từ cuối epoch hoàn tất gần nhất. Phần epoch đang dở phải chạy lại. AMP sang FP32 giữ model/optimizer/EMA và bỏ scaler cũ; FP32 sang AMP khởi tạo scaler nếu checkpoint không có trạng thái scaler. Metadata ghi chuyển chế độ. FP32 có thể tốn thêm VRAM/thời gian; không đổi segment trong run đang resume. [PyTorch: lưu và resume AMP](https://docs.pytorch.org/tutorials/recipes/recipes/amp_recipe.html).

Để áp dụng trainer mới vào phiên Colab hiện tại, upload `colab_fix_amp_training.py`, chạy `%run -i /content/colab_fix_amp_training.py`, rồi `train_run('lite', LITE_DIR, LITE_EPOCHS, 3e-4, 15)`. Bản vá chỉ thay train.py, giữ backup code trước sửa, cài logger và đặt TRAIN_NO_AMP=True; nó chưa tự bắt đầu train, chưa thay đổi WAV, manifest hoặc checkpoint. Không chạy lại cell ghi module/cấu hình cũ sau bản vá.

Để nghe model mới:

```bash
python -m audio_sep.inference "/path/song.wav" \
  --checkpoint runs/lite_v2/best_model.pth --device cuda \
  --output outputs/lite_v2
```

Nghe cùng một đoạn giữa mixture, ground truth và estimate; chú ý giọng hát bị mất, nhạc lọt vào vocals, tiếng transient và stereo. Khi vẽ spectrogram, dùng cùng giới hạn dB và cùng mốc thời gian; không tự cắt sample để che lỗi alignment, không chuẩn hóa từng ảnh/từng stem riêng khi cần so mức âm lượng.
