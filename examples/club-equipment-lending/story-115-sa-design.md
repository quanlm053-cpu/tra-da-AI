# Thiết kế xác nhận giao thiết bị

Bàn giao BA viết SRS và prototype cho Story #115, task SA #132.

## HLD

Giao diện quản lý mở yêu cầu đã duyệt và xác nhận giao. API cùng origin dùng phiên và kiểm tra quyền từ #111. Microsoft SQL Server là nguồn trạng thái chung. Một giao dịch T-SQL kiểm tra thiết bị còn được giữ hay đã rảnh, cập nhật yêu cầu và lưu sự kiện giao. Sau commit, quản lý nhận yêu cầu đã cập nhật và thành viên thấy trạng thái mới khi tải lại danh sách hoặc chi tiết của mình qua API #113.

Mỗi ID thiết bị đại diện một tài sản vật lý. Lịch theo #112 tính giờ bận từ các khoảng đặt của yêu cầu `APPROVED` và `HANDED_OVER`. Tình trạng giữ thực tế kéo dài từ khi giao đến khi xác nhận nhận lại. Lượt trước đã quá giờ đặt vẫn chặn giao lượt sau. Thiết kế cho phép giao một yêu cầu đã duyệt khi thiết bị rảnh, kể cả ngoài giờ đặt, vì tiêu chí chưa quy định cửa sổ giao.

## Schema và phụ thuộc

| Bảng | Hợp đồng |
|---|---|
| `users`, `equipment` | PK `id int` theo migration #111. Vai trò `MANAGER` lấy từ người dùng của phiên. |
| `loan_requests` | PK `id`, FK `equipment_id`, `borrower_id`, thời gian đặt `start_at`, `end_at` và `created_at` dạng `datetime2(3)` UTC. CHECK `start_at < end_at` và CHECK trạng thái thuộc `PENDING`, `APPROVED`, `REJECTED`, `HANDED_OVER`, `RETURNED`. Thiết bị, người mượn và giờ đặt cố định sau khi tạo. |
| `loan_events` | PK `id`, FK `request_id` và `actor_id` bắt buộc. `from_status`, `to_status` bắt buộc, cùng miền với trạng thái yêu cầu. `occurred_at datetime2(3)` UTC bắt buộc. Bản ghi `APPROVED → HANDED_OVER` là nguồn người giao và giờ giao. |

Thêm chỉ mục unique có điều kiện để bảo vệ tối đa một yêu cầu đang giữ thiết bị, kể cả khi có đường ghi bỏ qua kiểm tra nghiệp vụ. Ví dụ với schema `dbo`, dùng quy ước schema của migration hiện hành khi triển khai.

```sql
CREATE UNIQUE INDEX UX_loan_requests_equipment_handed_over
ON dbo.loan_requests (equipment_id)
WHERE status = 'HANDED_OVER';
```

Trước khi tạo chỉ mục, kiểm tra dữ liệu hiện có bằng `GROUP BY equipment_id HAVING COUNT(*) > 1` trên các dòng `HANDED_OVER`. Nếu phát hiện vi phạm, dừng migration để xác minh trạng thái giữ thiết bị. Dùng chỉ mục lịch theo `(equipment_id, status, start_at)` của thiết kế trước và giữ sự kiện giao ở bảng lịch sử chung.

- #111 đã bàn giao phiên, CSRF, vai trò và ID thiết bị. Checkout hiện có migration nền và kiểm tra quyền tại API.
- #112 đang triển khai bảng yêu cầu và lịch. #113 cung cấp tạo yêu cầu, danh sách và chi tiết theo chủ sở hữu. #114 cung cấp yêu cầu đã duyệt, sự kiện và quy ước khóa. Trước triển khai #115, đối chiếu migration thực tế, hình dạng phản hồi và đường đọc quản lý từ các Story này. Prototype dùng dữ liệu tổng hợp độc lập.
- #116 dùng cùng thứ tự khóa để đổi `HANDED_OVER → RETURNED`. Sau commit, chỉ mục giải phóng thiết bị và lịch loại lượt đã trả. Triển khai nhận lại thuộc #116.

## API và quyền

`POST /loan-requests/{id}/handover` dùng cookie phiên và header `X-CSRF-Token`, không cần payload. ID phải hợp lệ theo kiểu khóa của yêu cầu. API kiểm tra phiên còn hiệu lực, vai trò quản lý và CSRF trước khi đọc yêu cầu. Actor lấy từ phiên, giờ giao lấy từ SQL Server. Thành viên đọc danh sách và chi tiết với điều kiện `borrower_id = session.user_id`. Lịch chỉ trả thông tin khung giờ.

Thành công trả `200` sau commit với đối tượng yêu cầu theo DTO #114, gồm `status: "HANDED_OVER"`. Nhật ký nội bộ giữ actor và thời điểm. Lỗi dùng trường `code` theo hợp đồng API hiện hành.

| HTTP | Code | Hành vi |
|---|---|---|
| 400 | `INVALID_REQUEST` | ID sai định dạng. |
| 401 | `AUTH_REQUIRED` | Thiếu phiên hoặc phiên hết hạn. |
| 403 | `FORBIDDEN` / `CSRF_INVALID` | Sai vai trò hoặc thiếu CSRF hợp lệ. |
| 404 | `NOT_FOUND` | ID hợp lệ nhưng yêu cầu không tồn tại. Áp dụng cùng mã cho chi tiết ngoài quyền sở hữu. |
| 409 | `INVALID_TRANSITION` | Yêu cầu hiện không ở `APPROVED`. Tải lại để xem trạng thái. |
| 409 | `EQUIPMENT_IN_USE` | Thiết bị vẫn đang được giữ. Vui lòng xác nhận nhận lại trước khi giao lượt này. Yêu cầu vẫn `APPROVED`. |
| 500 | `INTERNAL_ERROR` | Lỗi ngoài nghiệp vụ. Tải lại chi tiết trước khi thử lại nếu kết quả lưu chưa rõ. |

Màn quản lý chỉ cho xác nhận từ chi tiết `APPROVED` của luồng #114. Hàng đợi duyệt hiện phục vụ `PENDING`, nên BA cần thể hiện đường mở chi tiết của lượt đã duyệt, kể cả khi đã rời hàng đợi. Thông báo xung đột chỉ nêu tình trạng thiết bị. Hiển thị thời gian cho người dùng theo `Asia/Bangkok`.

## LLD giao dịch và cạnh tranh

Vòng đời hợp lệ gồm `PENDING → APPROVED → HANDED_OVER → RETURNED` và `PENDING → REJECTED`. Mọi lệnh quản lý đổi trạng thái dùng giao dịch `READ COMMITTED` và thứ tự khóa thiết bị rồi khóa yêu cầu. Truy vấn tham số hóa, dùng cùng kết nối đến khi kết thúc giao dịch.

1. Bắt đầu giao dịch với `SET XACT_ABORT ON`. Đọc `equipment_id` theo ID yêu cầu để định tuyến khóa, không giữ khóa cập nhật trên yêu cầu ở bước này. Thiếu yêu cầu trả 404 sau rollback.
2. Đọc dòng thiết bị theo PK với `WITH (UPDLOCK, HOLDLOCK)`. Sau khi lấy được khóa, đọc lại yêu cầu theo PK với `WITH (UPDLOCK, HOLDLOCK)` và xác nhận cùng thiết bị. Kiểm tra trạng thái nguồn. Nếu sai, rollback và trả `INVALID_TRANSITION`.
3. Dùng câu lệnh riêng sau khi lấy khóa để kiểm tra `EXISTS` trên `equipment_id = @equipment_id AND status = 'HANDED_OVER' AND id <> @request_id`. Nếu có, rollback và trả `EQUIPMENT_IN_USE`. Kiểm tra này không lọc theo giờ đặt hay người mượn.
4. Gán `@now = SYSUTCDATETIME()` vào biến `datetime2(3)`. Cập nhật `status = 'HANDED_OVER'` với điều kiện `id = @request_id AND status = 'APPROVED'` và xác nhận đúng một dòng đổi. Ghi sự kiện cùng giao dịch với `@request_id`, `@actor_id`, `APPROVED`, `HANDED_OVER`, `@now`. Chuẩn bị dữ liệu phản hồi từ dòng vừa cập nhật và chỉ gửi sau commit.
5. Với lỗi SQL, rollback giao dịch còn mở. Chỉ ánh xạ vi phạm đúng chỉ mục giữ thiết bị sang `EQUIPMENT_IN_USE`. Các lỗi khác dùng cơ chế lỗi chung. Lệnh gửi lại sau lần giao đã commit nhận `INVALID_TRANSITION`, giữ nguyên một sự kiện.

### Duyệt trùng lịch và tương tác với giao nhận

Khi duyệt ở #114, sau khóa thiết bị và kiểm tra `PENDING`, chạy câu lệnh riêng tìm các yêu cầu khác cùng thiết bị ở `APPROVED` hoặc `HANDED_OVER` với `existing.start_at < requested.end_at AND requested.start_at < existing.end_at`. Khoảng đặt là `[start, end)`. Hai lượt duyệt trùng nhau được tuần tự hóa trên cùng dòng thiết bị. Lượt sau đọc kết quả commit của lượt trước và trả `409 SCHEDULE_CONFLICT`, giữ `PENDING`. Hai khoảng sát biên có thể cùng được duyệt. Giao một lượt trong số đó vẫn chặn lượt kế tiếp cho đến khi nhận lại.

Hai lệnh giao cho hai yêu cầu đã duyệt của cùng thiết bị cạnh tranh trên cùng khóa. Lượt sau thấy lượt đầu đã giao hoặc được xét tiếp nếu lượt đầu rollback. Hai lệnh giao cùng một yêu cầu cho một thành công và một `INVALID_TRANSITION`. Nếu giao cạnh tranh với nhận lại, giao thành công khi đọc sau commit nhận lại và thiết bị đã rảnh. Nếu giao lấy khóa trước lúc nhận lại, trả xung đột để quản lý thử lại sau.

## Bàn giao BA

| Ca | Kết quả cần đặc tả |
|---|---|
| Giao thành công | Quản lý nhận trạng thái đã giao. Thành viên sở hữu thấy trạng thái sau tải lại. Nhật ký có đúng actor từ phiên và một thời điểm UTC từ SQL Server. |
| Lượt trước quá hạn | Dùng DEMO-01 có hai khoảng đã duyệt sát biên. Sau khi giao lượt đầu và qua giờ kết thúc, giao lượt sau báo thiết bị vẫn đang được giữ. Lượt sau vẫn đã duyệt. DEMO-02 có thể giao độc lập. |
| Quyền và trạng thái | Khách nhận 401, thành viên gọi trực tiếp nhận 403, quản lý thiếu CSRF nhận 403. Yêu cầu không ở trạng thái đã duyệt nhận 409. Các ca lỗi giữ nguyên yêu cầu và lịch sử. |
| Tranh chấp và lỗi lưu | Dùng hai kết nối SQL Server kiểm tra giao đồng thời cùng thiết bị, giao lặp cùng yêu cầu, lỗi ghi sự kiện và giao sau khi nhận lại. Đối chiếu API, trạng thái và số sự kiện sau mỗi ca. |
| Mất phản hồi | Vô hiệu hóa nút khi đang gửi. Nếu mất phản hồi, tải lại chi tiết. Nếu đã giao, hiển thị kết quả đã lưu. Nếu vẫn đã duyệt, cho phép thử lại. |

Đã đối chiếu tiêu chí và bàn giao #111–114 qua MCP Lending, cùng migration nền và middleware trong checkout. Các ca giao dịch SQL Server là tiêu chí kiểm tra tích hợp khi có migration nghiệp vụ và các endpoint phụ thuộc.
