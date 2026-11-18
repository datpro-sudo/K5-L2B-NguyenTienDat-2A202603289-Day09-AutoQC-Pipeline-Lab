# Báo cáo Day 09 — Nguyen Tien Dat, 2A202603289

## 1. Kết luận trước
Pipeline nhận 224 ảnh, loại 22 tại cửa vào (8 trùng byte, 4 trùng gần, 5 rò rỉ test, 2 hỏng, 3 quá nhỏ) và giữ 202 ảnh. Sau 80 lượt duyệt mô phỏng, không còn lỗi bắt buộc nhưng còn cảnh báo ở 62/202 ảnh (30,7%), cao hơn ngưỡng 10%; kết luận **Hold**. `clean_v1` là bản nháp, chưa được phát hành.

## 2. Lỗi và phân việc
`02_error_list_v1` gộp lỗi cửa vào với vòng QC đầu: 58 dòng ERROR (22 lỗi ở cửa vào, 36 lỗi trên 202 ảnh được nhận) và 401 dòng WARN. Số dưới đây là ảnh/dòng bị gắn cờ; `BAD_CLASS_NAME` đếm tệp/tên lớp, `CLASS_RARE` đếm thống kê toàn tập.

| Mã lỗi | Ảnh / dòng | Ai xử lý | Cách xử lý |
|---|---:|---|---|
| BAD_CLASS_ID | 6 / 6 | Máy | Xóa dòng có ID ngoài miền |
| BAD_CLASS_NAME | 1 tệp / 2 tên lớp | Máy | Chuẩn hóa tên lớp trong `data.yaml` |
| BAD_FORMAT | 3 / 3 | Máy | Xóa dòng sai định dạng |
| BAD_SIZE | 3 / 3 | Máy | Loại ảnh ở cửa vào |
| BOX_HUGE | 3 / 3 | Người | Cảnh báo box quá lớn, cần xem ngữ nghĩa |
| BOX_OUT_OF_IMAGE | 8 / 8 | Máy | Cắt box vào biên ảnh |
| BOX_TINY | 4 / 6 | Người | Xem box nhỏ có hợp lệ không |
| BOX_ZERO | 4 / 4 | Máy | Xóa dòng box rỗng |
| CLASS_RARE | 1 tập / 4 box | Người | Xem lại phân bố lớp hiếm |
| CORRUPT_IMAGE | 2 / 2 | Máy | Loại ảnh không đọc được |
| DUP_BOX | 7 / 7 | Máy | Xóa dòng box lặp |
| DUP_IMAGE_EXACT | 8 / 8 | Máy | Loại ảnh trùng byte |
| DUP_IMAGE_NEAR | 4 / 4 | Máy | Loại ảnh trùng gần |
| EMPTY_LABEL | 12 / 12 | Người | Xác nhận ảnh nền hay nhãn bị thiếu |
| LEAK_TEST | 5 / 5 | Máy | Loại ảnh trùng tập test |
| MISSING_LABEL_FILE | 6 / 6 | Người | Máy chỉ chuyển người gán, không tự tạo nhãn |
| POSSIBLE_FALSE_POS | 27 / 29 | Người | Xác minh dự đoán thừa |
| POSSIBLE_LOOSE_BOX | 45 / 58 | Người | Xác minh box lỏng |
| POSSIBLE_MISSING | 97 / 267 | Người | Xác minh vật thể có thể bị bỏ sót |
| POSSIBLE_WRONG_CLASS | 21 / 22 | Người | Xác minh lớp có thể bị gán sai |

Autofix ghi 35 thay đổi: 20 dòng bị xóa, 8 box được cắt, 1 lần chuẩn hóa lớp và 6 ảnh chuyển người gán. Hàng đợi có 147 ảnh; điểm ưu tiên cộng trọng số cảnh báo, độ tin cậy và các sửa cần kiểm tra. Ví dụ `img_0160` đứng đầu (109.727) vì có `POSSIBLE_MISSING` và `POSSIBLE_WRONG_CLASS`. Với ngân sách 80, mô phỏng chọn 80 ảnh đầu; chúng có 122 cờ ngữ nghĩa (`POSSIBLE_MISSING` 64, `POSSIBLE_LOOSE_BOX` 25, `POSSIBLE_WRONG_CLASS` 20, `POSSIBLE_FALSE_POS` 13). Đây là cờ cần xem, không phải 122 lỗi đã được xác nhận bởi người thật.

## 3. Calibration
| Tham số | Khởi đầu → chọn | Precision / Recall trước → sau | Đánh đổi |
|---|---|---|---|
| `duplicates.phash_dist` | 2 → **10** | `DUP_IMAGE_NEAR`: 1.00/0.50 → 1.00/0.67; exact giữ 1.00/1.00 | Calib bắt 4/6 ảnh trùng gần, không có FP. Chọn 10 thận trọng: ngưỡng 16 tăng recall lên 5/6 nhưng trên raw ghép nhầm hai cặp ảnh khác chủ đề. |
| `second_opinion.conf` | 0.25 → **0.1** | `POSSIBLE_LOOSE_BOX`: 0.29/0.40 → 0.38/0.60; `POSSIBLE_MISSING`: 0.50/1.00 → 0.40/1.00 | Recall box lỏng tăng; đổi lại báo động giả về thiếu nhãn tăng từ 8 lên 12. Cảnh báo chỉ đưa người xem, không tự sửa. |

Điểm có thể đánh lừa: calibration chỉ gồm 39 ảnh có lỗi chèn, không đại diện mọi lỗi trong raw; hơn nữa, mô hình có thể báo sai hoặc bỏ sót. Vì vậy đã kiểm tra các cặp trùng raw và không chọn ngưỡng chỉ vì recall calib cao.

## 4. Cửa chặn và điểm mù
Chạy thử `python -m pipeline.run --budget 0 --reports work/rep_nb --export-dir work/exp_nb`: kết quả **Rework**, còn 6 lỗi bắt buộc, mã thoát 20; `work/exp_nb/clean_v1` không được xuất. Điều này xác nhận ảnh thiếu nhãn không được máy tự bịa và gate chặn phát hành khi chưa có người gán.

Hai điểm mù có số liệu: ở calib, `DUP_IMAGE_NEAR` bỏ sót 2/6 ca; `POSSIBLE_LOOSE_BOX` bỏ sót 2/5 và `POSSIBLE_WRONG_CLASS` bỏ sót 1/6. Ngoài ra, 67/147 ảnh trong hàng đợi không nằm trong ngân sách 80; cảnh báo còn lại khiến tỷ lệ 62/202 vượt ngưỡng Hold. Các cảnh báo mô hình cần được xác minh, không thể xem là nhãn đúng/sai chắc chắn.

## 5. Train: raw vs clean
**Chưa chạy** — bỏ qua Colab theo yêu cầu; phần train là tùy chọn. Hơn nữa, kết quả hiện tại là Hold nên `clean_v1` chỉ là bản nháp, không dùng như bộ phát hành.

## 6. Quyết định và ghi chú AI
Quyết định cuối: **Hold**. Để xem xét Release, cần người gán/duyệt phần còn lại, xử lý cảnh báo cho tỷ lệ dưới 10%, rồi chạy lại pipeline và xác nhận không còn lỗi bắt buộc.

- Prompt chính: dựa trên docstring/test của repo để triển khai bốn module, calibrate hai ngưỡng, chạy pipeline và hoàn thiện báo cáo; bỏ qua train Colab.
- Kiểm chứng: đọc code và test; xác nhận autofix tác động lên working copy chứ không sửa `data/raw`; chạy đủ 79 test, kiểm tra calibration/cặp trùng và thử gate với ngân sách 0.
- Một lần AI sai: bộ second-opinion gắn `POSSIBLE_MISSING` nhưng có 12 false positive trên calib ở `conf=0.1`; vì vậy giữ nó ở vai trò cảnh báo, không tự xóa/sửa nhãn.
