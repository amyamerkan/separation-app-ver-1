# Số liệu và nguồn đối chiếu

Ngày tổng hợp: 01/11/2026. Phiên bản source: `58e0e5d`. Tài liệu tiến độ là nguồn về diễn biến dự án; mã hiện hành và checkpoint là nguồn xác định hệ thống đang triển khai. Không coi kế hoạch trong PDF là tính năng đã làm.

## Số liệu dùng vẽ biểu đồ

| Nguồn | SDR* trung bình dB | SDR* trung vị dB | Phase MAE độ | Leakage dB |
| --- | ---: | ---: | ---: | ---: |
| Vocals | 1,854 | 2,329 | 31,393 | -11,089 |
| Drums | 1,945 | 1,740 | 42,673 | -20,083 |
| Bass | 0,765 | 1,828 | 38,165 | -8,554 |

Nguồn: PDF `TIẾN ĐỘ TUẦN (1).pdf`, trang 14 đã kiểm tra bằng hình render. Theo tài liệu: 50 bài test MUSDB18-HQ, Tesla T4, segment 6 giây, overlap 25%, RTF trung bình 0,005. Chưa có CSV từng track, hash checkpoint hoặc giao thức timing gốc để tái kiểm chứng.

SDR* giữ tên lịch sử trong PDF. Công thức ở trang 11 là SNR waveform, không phải BSS Eval SDR đã được xác nhận. Không dùng 0 cho Other chưa được báo. Không suy ra khoảng tin cậy, độ lệch chuẩn hoặc đường cong train từ các số tổng hợp.

CSV: `data/ket_qua_tuan4.csv`. Hình: `figures/week4_sdr.png` và `.svg`.

Bảng nghiên cứu ở `data/sdr_nghien_cuu.csv` lấy từ [bảng công bố của Spleeter](https://github.com/deezer/spleeter/blob/master/paper.md). Chỉ số đó được vẽ riêng trong `figures/literature_sdr.png`; không đặt SNR V2 vào cùng bảng xếp hạng. Không phải kết quả chạy lại các model trong dự án.

## Checkpoint xác minh trực tiếp

| Thuộc tính | Giá trị |
| --- | --- |
| File | `DemucsLite_deploy/backend/checkpoints/best_model.pth` |
| Epoch | 100 |
| Trọng số chọn | EMA |
| best_snr_db | 3.539064884185791 |
| Số phần tử tham số | 10.309.704 |
| Dung lượng | 41.307.935 byte |
| SHA-256 | `c8afd78e8f49dfcde538f008345c9bdd64c305d88da9386b50138ebe3b36c5d3` |

Metadata và hash được đọc lại trong phiên biên soạn. Không có `history`, `training_config` đầy đủ hoặc kết quả từng source trong export. Vì vậy bảng hyperparameter báo cáo là mặc định của code, không được xem là chứng nhận cấu hình thực chạy của toàn bộ run.

## Khác biệt cần giữ khi trình bày

| Nội dung trong tiến độ hoặc hồ sơ cũ | Hiện trạng theo source |
| --- | --- |
| Tuần 1 có hướng spectrogram, ba nguồn | V2 dùng waveform và bốn nguồn |
| BiLSTM một lớp ở model nền tảng | Checkpoint V2 có hai lớp |
| Split 85/15 | Pipeline V2 dùng danh sách chính thức 86/14 |
| Tuần 6 nói pipeline đưa cả bài vào model | Pipeline hiện gọi overlap_add 6 giây, overlap 0,5 |
| Client mixer chưa có ở tuần 6 | Java/XML đã có mixer, solo/mute và lưu WAV |
| Tải đa luồng dự kiến | StudioSession hiện tải lần lượt bốn track |
| Đồng bộ chính xác tuyệt đối dự kiến | Bốn MediaPlayer; chưa đo sample drift |
| Đưa lên cloud | Có S3/GCS adapter; mới có bằng chứng local |
| Hủy xử lý | Dừng phía client, chưa có endpoint cancel server |
| Xuất bản phối | Lưu stem WAV gốc; slider không render vào WAV |
| Tài liệu chẩn đoán nói chưa có V2 đã train | Bị thay thế bởi checkpoint epoch 100 đã xác minh |
| verification.json ghi Android minSdk 36, 57 warning | Thuộc app cũ; app hiện minSdk 29, lint lưu 49 warning |

## Kiểm thử đã được đối chiếu

- `DemucsLite_deploy/verification.json`: backend 14 pass; Lite CPU 36 pass; resolver offline 8 pass. Đây là kết quả ghi nhận trước, không phải lượt chạy mới ngày 01/11/2026.
- API smoke của gói: input tổng hợp stereo 1 giây, đủ bốn output PCM16, 44.100 frame, finite. Không phải đánh giá chất lượng tách nhạc.
- `app/build/test-results/testDebugUnitTest/TEST-com.example.demucslite.AudioFilesTest.xml`: 3 pass.
- `app/build/test-results/testDebugUnitTest/TEST-com.example.demucslite.ExampleUnitTest.xml`: 1 pass; đây là test mẫu, không là kiểm thử chất lượng sản phẩm.
- `app/build/reports/lint-results-debug.xml`: 49 warning, không có error; XML ngày 25/10/2026.
- Có mã instrumentation nhưng chưa có report chạy tương ứng trong bộ hồ sơ dùng cho báo cáo.

## Phép tính bổ sung

- Trung bình ba nguồn tuần 4: `(1.854 + 1.945 + 0.765) / 3 = 1.521333333` dB.
- Median trừ mean: Vocals `0.475`, Drums `-0.205`, Bass `1.063` dB.
- Chênh tham số: `10314056 - 10309704 = 4352`, giảm khoảng `0.0422%`.
- Dung lượng: `41307935 / 1048576 = 39.3943` MiB.
- Crop 6 giây: `6 * 44100 = 264600` sample/kênh.
- Shape tính từ code: padding `265556`, encoder lengths `66388, 16596, 4148, 1036, 258`.

## Dữ liệu cần có để nâng cấp kết luận

1. `history.csv`, `config.json`, manifest/audit và checkpoint đầy đủ của run V2.
2. JSON test 50 bài của từng checkpoint với cùng metric và cách tổng hợp.
3. Kết quả museval nếu muốn ghi BSS Eval SDR.
4. Log timing, RAM/VRAM và thiết bị cho V2; tách inference với toàn luồng app.
5. Audio mẫu và biên bản nghe thử; phép đo độ lệch phát bốn stem.

Không điền dữ liệu ước đoán vào những mục trên. Nếu có benchmark mới, giữ một cột nguồn và một cột cấu hình cho mỗi bảng số liệu.
