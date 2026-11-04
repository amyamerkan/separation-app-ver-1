# Hướng dẫn hoàn thiện báo cáo

## Định dạng đã áp dụng

- Khổ A4, Times New Roman; nội dung 13 pt, giãn dòng 1,5, canh đều.
- Lề trái 3 cm, phải 2 cm, trên/dưới 2,5 cm; đầu dòng 1 cm.
- Chương 16 pt đậm; mục 14 pt đậm; bảng 11–12 pt; caption 11,5 pt.
- Chương mới bắt đầu trang mới; có mục lục, danh mục hình, danh mục bảng, viết tắt và số trang.
- Bìa để trống trường/khoa, sinh viên, MSSV, lớp, giảng viên theo yêu cầu.

Đây là cấu hình báo cáo học thuật thông dụng đã chọn cho bản này. Chưa có quy định cụ thể của khoa để chứng nhận khớp tuyệt đối. Khi có mẫu khoa, chỉ cần đối chiếu và chỉnh style/lề/bìa.

## Chỉnh sửa nội dung

`BAO_CAO_DU_AN.md` là nội dung chính. `SO_DO_HE_THONG.md` chứa mã Mermaid. `SO_LIEU_VA_NGUON.md` ghi dấu vết số liệu và sự khác nhau giữa kế hoạch với bản đã triển khai. Các tệp CSV có thể mở bằng Excel nhưng không có giá trị giả cho dữ liệu thiếu.

Sau khi sửa Markdown, chạy script dựng Word nếu muốn giữ hai bản đồng nhất. Nếu sửa trực tiếp Word, cần phản ánh thay đổi về Markdown khi tiếp tục quản lý bằng Git.

## Cập nhật mục lục

Mục lục Word chứa trường TOC với nội dung đã điền số trang tại thời điểm dựng. Các mục có liên kết nội bộ. Sau khi thay đổi nội dung trong Word, chọn toàn bộ tài liệu và cập nhật trường, hoặc nhấp mục lục và chọn cập nhật toàn bộ. Trên macOS, phím F9 có thể cần Fn tùy cài đặt bàn phím.

Danh mục hình/bảng là các liên kết và trường PAGEREF tới caption có bookmark. Cập nhật các trường sau khi thêm trang. Nếu thêm một hình hoặc bảng mới, thêm entry danh mục tương ứng hoặc chạy lại script; cập nhật PAGEREF không tự tạo entry mới.

## Trước khi gửi giảng viên

1. Điền thông tin bìa và tên đề tài chính thức.
2. Xác nhận cách gọi môn học và yêu cầu lề/font của khoa.
3. Giữ chú thích SDR* và phạm vi validation/test khi chỉnh Chương 4.
4. Nếu đã có log V2 mới, bổ sung bảng và hình theo nguồn thật.
5. Cập nhật mục lục, kiểm tra các trang hình/bảng và xuất PDF nếu cần nộp.

Tài liệu được chuẩn bị để bạn rà soát và gửi; không có email hay tin nhắn nào được gửi cho giảng viên trong quá trình tạo bộ báo cáo.

## Dựng lại hình và Word

Chạy các lệnh dưới đây từ thư mục `Bao_cao/` ở gốc dự án. Các script nằm trong `scripts/`; bản Word được tạo ngay trong `Bao_cao/`. Môi trường cần `python-docx`, Pillow, matplotlib; cập nhật số trang tự động từ PDF cần `pypdf`. Trên máy đang biên soạn, Python và LibreOffice dùng runtime đi kèm Codex; không thay đổi môi trường app.

```text
python scripts/build_figures.py
python scripts/build_report.py
```

Sau khi dựng Word, render bằng `render_docx.py` của kỹ năng Documents. Script `index_pages.py` đọc PDF đã render để lập bản đồ số trang; chạy lại `build_report.py --page-map PATH` rồi render lại để kiểm tra. Đây là bước cần thiết nếu tái tạo tài liệu ngoài Word, không nên giữ số trang cache của một bản cũ.
