# Bộ báo cáo dự án DemucsLite

Bộ tài liệu gồm báo cáo bốn chương, kết luận, tham khảo và phụ lục; bảy sơ đồ thiết kế, hai biểu đồ so sánh, ảnh giao diện và các bảng kỹ thuật.

| Tệp hoặc thư mục | Nội dung |
| --- | --- |
| [BAO_CAO_DU_AN.md](BAO_CAO_DU_AN.md) | Toàn bộ nội dung báo cáo |
| [SO_DO_HE_THONG.md](SO_DO_HE_THONG.md) | Bảy sơ đồ Mermaid có thể chỉnh sửa |
| [SO_LIEU_VA_NGUON.md](SO_LIEU_VA_NGUON.md) | Số liệu, phạm vi xác minh, khác biệt phiên bản |
| [HUONG_DAN_HOAN_THIEN.md](HUONG_DAN_HOAN_THIEN.md) | Font/lề, cập nhật mục lục, chuẩn bị nộp |
| `figures/` | Sơ đồ và biểu đồ PNG/SVG; công thức và ảnh app |
| `data/` | CSV trích số liệu và JSON checkpoint |
| `scripts/` | Dựng hình, dựng Word và đối chiếu số trang |

Bản Word nằm ngay trong thư mục này: [Bao_cao_du_an_DemucsLite.docx](Bao_cao_du_an_DemucsLite.docx). Nội dung dùng Times New Roman; bìa để trống thông tin cá nhân theo yêu cầu.

Lưu ý chính: “SDR” của báo cáo tuần 4 sử dụng định nghĩa SNR waveform; best validation SNR của V2 là 3,539065 dB. Không so trực tiếp hai số này để kết luận mức cải thiện hoặc ghép chúng với BSS Eval SDR công bố. Các giới hạn và nguồn được trình bày trong Chương 4.

Tất cả Word và Markdown nằm trực tiếp trong `Bao_cao/` ở gốc dự án. Bốn thư mục con `figures/`, `diagrams/`, `data/`, `scripts/` lưu tài nguyên và công cụ dựng lại. Bản Word có tiền tố “Bản sao” được giữ nguyên từ thư mục đã giải nén.
