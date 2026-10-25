# Vì sao notebook hiện tại tách âm chưa tốt

Phân tích này dựa trên **code và output được lưu trong `main (1).ipynb`**, sơ đồ luồng người dùng gửi, metadata dataset và một checkpoint cũ tìm thấy trên máy. Chưa có audit toàn bộ audio trong Drive hoặc kết quả nghe/benchmark của model mới. Các nguyên nhân bên dưới phân biệt lỗi có bằng chứng với giả thuyết cần kiểm chứng.

## Kết quả đang cho thấy gì?

Output đã lưu ở epoch 46 ghi trung bình **2,19 dB**, trong đó vocals **−2,97 dB**, drums 4,15 dB, bass 3,79 dB, other 3,77 dB. Vocals là điểm yếu rõ ràng; trung bình bốn nguồn che khuất vấn đề này. Với công thức notebook `10 log10(E_target/E_error)`, một giá trị −2,97 dB nghĩa là năng lượng sai số lớn hơn năng lượng target ở các entry được chấm; nó không tự xác định sai số đó là tiếng nhạc lọt vào hay giọng bị mất. Giá trị log là trung bình nhiều entry, nên không diễn giải thành một tỷ lệ năng lượng duy nhất cho toàn bộ dataset.

Notebook gọi metric này là `SDR`, nhưng đây là **SNR của sai số waveform**, khác BSS Eval SDR và cũng khác SI-SDR. Hàm SI-SDR loss đã có riêng, song output “SDR” không phải kết quả hàm đó. Vì vậy không thể đối chiếu trực tiếp 2,19 dB với bảng SDR của paper Demucs. [Le Roux và cộng sự, SDR/SI-SDR](https://arxiv.org/abs/1811.02508)

Log tiếp tục tới epoch 52 rồi có `KeyboardInterrupt`. Code đang lưu đặt `EPOCHS=150`, trong khi log in `/200`; do đó output không khớp hoàn toàn với trạng thái cell hiện tại. Không thể khẳng định chạy lại các cell hiện tại sẽ tái tạo đúng run đó. Cần gắn checkpoint với config, manifest, phiên bản code và lịch sử riêng cho từng run.

Checkpoint local [demucs_lite_best.pth](</Users/amyas/HK1 26-27/DACNTT/demus-lite/checkpoints/demucs_lite_best.pth>) đọc được ghi **epoch 106**, `best_val_loss=0.054775565`, với **10.314.056 tham số**. Nó thiếu `loss_config` và metric best validation SDR/SNR, nên chưa truy vết được đầy đủ cách chấm. Checkpoint này không khớp log notebook dừng ở epoch 52; số 2,19 dB và vocals −2,97 dB ở trên là bằng chứng về run trong log, không phải kết quả đã đo lại của checkpoint epoch 106. Không so loss 0,0548 và 0,0821 để kết luận chất lượng tốt hơn khi chưa biết chúng dùng cùng mục tiêu, dữ liệu và cấu hình đánh giá.

## Những nguyên nhân chính trong code

| Bằng chứng | Tác động có cơ sở | Thay đổi trong bộ code mới |
|---|---|---|
| L1 trung bình theo biên độ, STFT chuẩn hóa bằng norm toàn batch/source | Source lớn chi phối loss; vocals nhỏ có thể được ưu tiên ít hơn dù sai tương đối lớn | Cân bằng theo RMS từng item/source, với floor theo mixture để tránh khuếch đại source gần im lặng |
| STFT lấy trung bình L/R trước khi tính loss | Không nhìn thấy đầy đủ lỗi stereo; hai kênh ngược pha có thể triệt tiêu khi gộp mono | Giữ cả hai kênh trong loss |
| FFT 256/512/1024 ở 44,1 kHz | Chỉ khoảng 5,8/11,6/23,2 ms; độ phân giải tần số hạn chế với bass/harmonic | Thêm độ phân giải 512/1024/2048/4096; vẫn giữ waveform loss |
| Có penalty tương quan residual với source khác | Các nhạc cụ thật có thể tương quan; penalty này không tương đương đo leakage và có thể tạo mục tiêu xung đột | Bỏ heuristic tương quan, dùng supervised waveform/STFT/SI-SDR và phạt estimate khi target im lặng |
| 85 bài train × 8 crop = 680 crop/epoch | Phủ các vị trí trong bài còn ít mỗi epoch; tăng epoch đơn thuần chưa giải quyết mục tiêu loss lệch | 86 bài × 32 crop ngẫu nhiên/epoch; remix từ toàn pool train ở mức sample |
| Chọn/giảm LR/early stopping chủ yếu theo val loss | Tổng loss tốt lên không bảo đảm vocals hoặc chất lượng nghe tốt hơn | Chọn checkpoint và scheduler theo validation SNR, ghi riêng từng stem, so raw/EMA |
| HPO chỉ 1 epoch, tối đa 10 batch train/5 batch val; trial dùng hệ số loss khác nhau | Loss nhỏ hơn có thể chỉ vì hệ số nhỏ hơn; thời gian này chưa đủ kết luận kiến trúc nào tốt hơn | So cùng metric, cùng split và ngân sách train; cấu hình mới được ghi là điểm khởi đầu |

Một ví dụ cụ thể về cân bằng loss: ở epoch 46, `source_l1=0.0300`, `spectral=0.5744`. Nếu run dùng trọng số `spectral_weight=0.08` như cell hiện tại, riêng spectral đóng góp khoảng **0,0460**, lớn hơn L1 khoảng **1,53 lần**. Đây là lý do cần ghi và xem từng thành phần loss; không nên thấy hệ số 0,08 rồi suy ra spectral là nhỏ. Vì log/cell không khớp hoàn toàn, phép tính này là phân tích có điều kiện theo config hiện tại, không chứng nhận config thực của checkpoint.

Loss STFT magnitude cũng không trực tiếp ràng buộc phase; waveform loss phải tiếp tục đảm nhận phần này. Thêm FFT lớn hơn hoặc SI-SDR không tự bảo đảm tiếng nghe sạch hơn. Cần đánh giá bằng các bài cố định và nghe các lỗi cụ thể.

## Những điều không nên quy lỗi nhầm

**Validation/test đã có `augment=False` trong notebook gửi.** Code đặt crop cố định và đọc mixture gốc; không có bằng chứng phiên bản hiện tại augment validation. Comment nói bản cũ từng thiếu tham số không chứng minh run đính kèm vẫn mắc lỗi đó.

**Split hiện tại theo bài, không theo đoạn.** Script chọn ngẫu nhiên 15 bài từ 100 bài train, để lại 85 bài; chưa có bằng chứng crop của cùng bài bị chia sang cả train và validation. Chuyển sang danh sách chính thức 86/14 giúp tái lập và đối chiếu nghiên cứu, chứ không phải bằng chứng sửa một vụ rò rỉ đã xảy ra. [Danh sách validation MUSDB](https://github.com/sigsep/sigsep-mus-db/blob/master/musdb/configs/mus.yaml)

**Pitch/speed đang dùng cùng factor và crop-start cho các stem.** Cách gọi này cố giữ alignment, rồi tính lại mixture bằng tổng các stem; không thể khẳng định augment đang làm lệch source chỉ từ hình vẽ. Tuy nhiên chưa kiểm tra được nội dung module ngoài `pitch_speed_perturb`, nên vẫn cần kiểm chứng chính phép biến đổi đó. Bản mới dùng gain/polarity/đổi L/R/remix để có pipeline dễ kiểm tra; pitch/tempo có thể được thêm sau một ablation rõ ràng.

**BiLSTM đã có ngữ cảnh dài.** Không nên kết luận model chỉ thấy vài millisecond vì convolution stride lớn. Kiến trúc gốc là waveform U-Net + BiLSTM; các convolution downsample tín hiệu, còn BiLSTM xử lý toàn chuỗi bottleneck. Điểm giới hạn là model học từ đầu với dataset nhỏ, thiếu các thành phần của Hybrid Transformer Demucs và chưa có quy trình lựa chọn chất lượng đủ tin cậy; đây không phải một lỗi hình dạng được chứng minh.

**Dataset chưa được chứng minh hỏng.** Script cũ chỉ đọc metadata mixture và không thực thi đầy đủ các hằng `EXPECTED_*`; nó không kiểm tra toàn bộ 5 stem, alignment hay mixture residual. Bản mới bổ sung audit để phát hiện vấn đề nếu có, không tuyên bố đã phát hiện file lỗi trong Drive.

## Vì sao kiến trúc “DemucsLite” chưa thể ngang model pretrained?

Tên và khung encoder–BiLSTM–decoder giống Demucs không có nghĩa đạt cùng chất lượng. HTDemucs phối hợp waveform, spectrogram và Transformer để trao đổi thông tin giữa hai miền; pretrained còn hưởng lợi từ dữ liệu và ngân sách huấn luyện lớn hơn. So sánh một model nhẹ từ đầu với pretrained là so cả kiến trúc, dữ liệu và quá trình huấn luyện. [Hybrid Transformers for Music Source Separation](https://arxiv.org/abs/2211.08553)

DemucsLite V2 bổ sung residual convolution có dilation ở các tầng sâu, normalization chung cho mixture, BiLSTM hai lớp với hidden size nhỏ hơn mỗi hướng và padding hai phía. Cấu hình mặc định có **10.309.704 tham số**, gần như cùng ngân sách tham số với **10.314.056** của model gốc; không thể suy ra V2 nhanh hơn hoặc dùng ít VRAM hơn chỉ từ con số này. Đây là ứng viên mới cần train và đo; checkpoint gốc không tương thích trực tiếp. Không gọi V2 là “tốt nhất” khi chưa có kết quả thực nghiệm.

Muốn nghe chất lượng mạnh sớm, dùng `htdemucs_ft` làm baseline. Muốn model riêng cho đồ án, train V2 và báo rõ giới hạn tốc độ/kích thước/chất lượng. Fine-tune `htdemucs` chỉ là thử nghiệm bổ sung: dùng LR nhỏ, lưu baseline epoch 0, và chỉ thay nó nếu validation cải thiện. [Demucs pretrained](https://github.com/facebookresearch/demucs#separating-tracks)

## Đánh giá cần làm trước khi kết luận đã cải thiện

1. Audit dữ liệu thật: đủ 150 bài, 5 WAV/bài, stereo 44,1 kHz, sample alignment, sample hữu hạn và residual hợp lý. Các probe của scanner chỉ kiểm tra vài vị trí; lỗi ngoài probe vẫn có thể tồn tại.
2. Giữ validation cố định 14 bài để chọn cấu hình. Model cũ dùng split ngẫu nhiên có thể đã train trên một số bài thuộc 14 bài đó; so old/V2 bằng validation mới có thể không công bằng. Trọng số pretrained cũng phải được báo rõ về dữ liệu đã thấy.
3. Sau khi cố định cấu hình, chạy **cùng 50 bài test** với checkpoint cũ, V2 và pretrained. Notebook cũ tạo `test_loader` nhưng không có bằng chứng đã chạy một báo cáo test đầy đủ.
4. Ghi SNR và SI-SDR từng source, tỷ lệ source active, hallucination ở đoạn im lặng, thời gian tách và cấu hình inference. Khi cần so bảng nghiên cứu MUSDB, chạy thêm đúng BSS Eval/museval thay vì đổi tên SNR thành SDR.
5. Nghe cùng những đoạn có vocals, bass, transient và im lặng. Hình spectrogram notebook cũ gộp mono và lấy `ref=np.max` riêng cho từng ảnh, nên che chênh lệch mức âm lượng; cắt về độ dài nhỏ hơn cũng có thể che lỗi alignment. Dùng cùng thang dB và kiểm tra số sample trước khi so.

Luồng mới vẫn giữ ý tưởng của sơ đồ: dataset → crop/augmentation → mixture → encoder/bottleneck/decoder → bốn stem → loss → backprop → optimizer → validation → checkpoint. Thay đổi quyết định nằm ở kiểm tra nhãn, cân bằng mục tiêu, lựa chọn checkpoint theo metric và đánh giá full-track. Toàn bộ 24 test code đã pass, gồm train/resume/export/evaluate với dữ liệu tổng hợp và forward/backward của HTDemucs cấu hình giảm; điều này kiểm tra pipeline, không chứng minh chất lượng trên nhạc thật. Lệnh chạy cụ thể nằm trong `README.vi.md`; job train Colab với dataset thật chưa bắt đầu vì quyền điều khiển trình duyệt bị từ chối, và chưa có benchmark chứng minh chất lượng vượt model cũ.
