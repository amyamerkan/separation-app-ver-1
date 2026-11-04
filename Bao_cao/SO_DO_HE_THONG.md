# Sơ đồ hệ thống DemucsLite

Các sơ đồ phản ánh mã nguồn hiện hành ngày 01/11/2026. Hình PNG và SVG dùng trong báo cáo nằm trong `figures/`. Mã Mermaid dưới đây có thể sửa trong Markdown hỗ trợ Mermaid. Riêng use case, Mermaid dùng flowchart mô phỏng ranh giới và ca sử dụng; bản hình trong Word vẽ actor, ellipse và quan hệ include theo cách trình bày UML.

## 1 Use case

```mermaid
flowchart LR
  U[Người dùng]
  subgraph SYS[Hệ thống DemucsLite]
    SEP([Tách nhạc từ tệp])
    CHECK([Kiểm tra tệp])
    AI([Phân tách bằng mô hình])
    STATUS([Theo dõi tác vụ])
    MIX([Nghe và điều chỉnh âm lượng solo mute])
    SAVE([Lưu WAV kết quả])
    CONFIG([Cấu hình server])
    DEMO([Chạy demo offline])
    SEP -. include .-> CHECK
    SEP -. include .-> AI
  end
  U --- SEP
  U --- STATUS
  U --- MIX
  U --- SAVE
  U --- CONFIG
  U --- DEMO
```

Nghe/lưu yêu cầu các stem đã sẵn sàng. Demo tạo âm thanh tổng hợp, không dùng AI. Không có đăng nhập hay dashboard quản trị trong bản hiện hành.

## 2 Kiến trúc triển khai

```mermaid
flowchart TB
  subgraph PHONE[Thiết bị Android]
    UI[Java XML và MainActivity]
    SESSION[StudioSession AndroidViewModel]
    HTTP[OkHttp]
    CACHE[Cache WAV và MediaPlayer]
    UI --> SESSION --> HTTP
    SESSION --> CACHE
  end
  subgraph SERVER[Một tiến trình FastAPI và một Uvicorn worker]
    API[API separate status health]
    JOB[JobStore dictionary trong RAM]
    BG[BackgroundTasks và khóa suy luận]
    DEC[SoundFile hoặc FFmpeg]
    MODEL[DemucsLite V2 và overlap add]
    EXP[Xuất 4 WAV PCM16]
    API --> JOB
    API --> BG --> DEC --> MODEL --> EXP
    BG --> JOB
  end
  HTTP -->|Upload và polling| API
  CKPT[Checkpoint epoch 100 EMA] --> MODEL
  EXP --> LOCAL[Storage local]
  EXP -. Khả năng mở rộng .-> CLOUD[S3 hoặc GCS]
  LOCAL -->|Tải WAV| HTTP
```

BackgroundTasks không phải worker độc lập. Nhánh S3/GCS có code, chưa có bằng chứng triển khai thực. File local còn sau restart không có nghĩa JobStore được phục hồi.

## 3 Tuần tự tách nhạc

```mermaid
sequenceDiagram
  actor U as Người dùng
  participant A as Android
  participant F as FastAPI
  participant J as JobStore
  participant P as Pipeline và model
  participant S as Storage
  U->>A: Chọn file và bắt đầu
  A->>F: POST /separate multipart file
  F->>F: Kiểm tra và lưu hết input
  F->>J: create(job_id, pending)
  F-->>A: job_id và pending
  F->>P: Đăng ký BackgroundTasks
  P->>P: Chờ khóa suy luận
  P->>J: processing
  P->>P: Decode, overlap-add, xuất PCM16
  loop Poll mỗi 1,8 giây đến trạng thái kết thúc
    A->>F: GET /status/{job_id}
    F->>J: get(job_id)
    J-->>F: Bản ghi hiện tại
    F-->>A: status và kết quả nếu đã có
  end
  alt Xử lý thành công
    P->>S: Ghi hoặc upload 4 WAV
    S-->>P: result_urls
    P->>J: done và result_urls
    A->>F: Lần poll tiếp theo
    F-->>A: done và result_urls
    loop Tải từng nguồn theo thứ tự
      A->>S: GET WAV
      S-->>A: Nội dung tệp
    end
    A-->>U: Mở mixer
  else Lỗi xử lý
    P->>J: failed và error
    P->>P: Xóa kết quả dở dang
    F-->>A: failed ở lần poll tiếp theo
    A-->>U: Thông báo lỗi
  end
  P->>P: finally xóa input tạm
```

Vòng polling chạy xen kẽ với pipeline; vị trí khối loop biểu diễn hoạt động đồng thời về mặt logic, không yêu cầu pipeline chờ vòng poll hoàn tất. Hủy phía client không hủy job server.

## 4 Trạng thái job

```mermaid
stateDiagram-v2
  [*] --> pending: upload hợp lệ
  pending --> processing: nhận khóa suy luận
  processing --> done: ghi đủ kết quả và URLs
  processing --> failed: ngoại lệ
  done --> [*]
  failed --> [*]
  note right of processing
    Chưa có canceled
    JobStore không bền vững qua restart
  end note
```

## 5 Lớp và phụ thuộc module

```mermaid
classDiagram
  class MainActivity {
    StudioSession session
    MediaPlayer[] players
    play()
    pause()
    exportTracks()
  }
  class StudioSession {
    Phase phase
    Stem[] stems
    String serverUrl
    start()
    cancel()
    select()
    setServer()
  }
  class Stem {
    String key
    File file
    float[] envelope
    int volume
    boolean solo
    boolean muted
  }
  class MainAPI {
    <<module>>
    separate_audio()
    get_status()
    health_check()
  }
  class Pipeline {
    <<module>>
    decode_audio()
    run_separation_pipeline()
    export_pcm_stems()
  }
  class JobStore {
    dict _jobs
    create()
    update()
    get()
  }
  class Job {
    <<dictionary_record>>
    status
    filename
    created_at
    updated_at
    result_urls
    error
  }
  class ModelLoader {
    <<module>>
    load_model()
    get_model()
  }
  class CloudStorage {
    <<module>>
    upload_folder()
  }
  MainActivity --> StudioSession
  StudioSession --> "0..4" Stem
  StudioSession ..> MainAPI : HTTP
  MainAPI ..> Pipeline
  MainAPI ..> JobStore
  Pipeline ..> JobStore
  Pipeline ..> ModelLoader
  Pipeline ..> CloudStorage
  JobStore o-- "0..*" Job
```

Job là dictionary, không phải model ORM. MainAPI, Pipeline, ModelLoader và CloudStorage là module Python, không phải các class được khai báo trong source. Stem[] có thể chưa tồn tại trước khi sẵn sàng; khi thành công có bốn phần tử.

## 6 Kiến trúc mạng

```mermaid
flowchart TB
  IN[Waveform B x 2 x T] --> N[Chuẩn hóa chung stereo và padding]
  N --> E1[Encoder 32] --> E2[Encoder 64] --> E3[Encoder 128 DConv]
  E3 --> E4[Encoder 256 DConv] --> E5[Encoder 512 DConv]
  E5 --> L[BiLSTM 2 lớp 256 ẩn mỗi chiều và Linear 512]
  L --> D5[Decoder 256 DConv] --> D4[Decoder 128 DConv]
  D4 --> D3[Decoder 64 DConv] --> D2[Decoder 32] --> D1[Decoder 8]
  E1 -. skip .-> D1
  E2 -. skip .-> D2
  E3 -. skip .-> D3
  E4 -. skip .-> D4
  E5 -. skip .-> D5
  D1 --> OUT[Cắt và hoàn nguyên B x 4 x 2 x T]
```

Số trong decoder là số kênh đầu ra; skip được cộng trước các phép biến đổi trong decoder. DConv bật ở ba mức sâu. Checkpoint tắt projection mixture_consistency sau forward.

## 7 Dữ liệu và huấn luyện

```mermaid
flowchart TB
  DATA[MUSDB18-HQ] --> AUDIT[Audit và manifest]
  AUDIT --> TR[86 train]
  AUDIT --> VA[14 validation]
  AUDIT --> TE[50 test giữ riêng]
  TR --> AUG[Crop ngẫu nhiên gain polarity đổi L R remix]
  AUG --> SUM[Tính mixture từ stem đã biến đổi]
  SUM --> TRAIN[Forward loss backward AdamW]
  TRAIN --> EMA[Cập nhật raw và EMA]
  VA --> FIX[Crop cố định không augmentation]
  FIX --> VAL[So raw EMA bằng validation SNR]
  EMA --> VAL
  VAL --> SCHED[Scheduler và early stopping]
  VAL --> SAVE[Lưu last best và xuất best_model]
  SCHED --> TRAIN
  SAVE --> FREEZE[Cố định checkpoint và cấu hình]
  FREEZE --> EVAL[Đánh giá full-track SNR SI-SDR]
  TE --> EVAL
```

Sơ đồ mô tả pipeline đã hiện thực. Sự tồn tại của luồng evaluation không chứng minh benchmark V2 đã được chạy đủ 50 bài.
