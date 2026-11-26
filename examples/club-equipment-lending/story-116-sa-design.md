# Thiết kế xác nhận nhận lại thiết bị

Bàn giao BA cho Story #116, task SA #134. Cơ sở thiết kế gồm tiêu chí Redmine #116, các bản bàn giao #111–115 qua MCP Lending và schema, middleware nền tảng trong workspace.

## HLD

Website và API dùng cùng origin qua HTTPS. API dùng phiên phía máy chủ, phân quyền theo vai trò và chống CSRF cho lệnh ghi. Microsoft SQL Server là nguồn trạng thái, lịch đặt và lịch sử giao nhận. Các thao tác ghi dùng T-SQL tham số hóa và giao dịch theo thiết bị vật lý. Kiến trúc nền tảng được mô tả trong [thiết kế #111](story-111-sa-design.md).

Quản lý chọn yêu cầu đã giao và xác nhận nhận lại. API chuyển `HANDED_OVER → RETURNED` và lưu sự kiện nhận lại trong một giao dịch. Sau commit, thành viên tải lại danh sách hoặc chi tiết yêu cầu của mình để thấy **Đã trả**. Lịch tra cứu mới loại khoảng đặt của yêu cầu đó. Lượt đã duyệt tiếp theo vẫn đi qua thao tác xác nhận giao của #115 để kiểm tra thiết bị đang rảnh.

## Schema và quy tắc dữ liệu

| Thành phần | Hợp đồng dùng cho #116 |
|---|---|
| `users`, `equipment` | ID kiểu `int` từ #111. Vai trò `MANAGER` lấy từ phiên. Một dòng thiết bị đại diện một tài sản vật lý. |
| `loan_requests` | `id` PK, `equipment_id` FK đến thiết bị, `borrower_id` FK đến người dùng, `start_at`, `end_at`, `created_at` kiểu `datetime2(3)` UTC. CHECK `start_at < end_at`. Thiết bị, người mượn và khoảng đặt cố định sau khi tạo. Ràng buộc trạng thái phải chấp nhận `PENDING`, `APPROVED`, `REJECTED`, `HANDED_OVER`, `RETURNED`. |
| `loan_events` | Dùng nhật ký đã thiết kế từ #114. `id` PK, `request_id`, `actor_id` là FK bắt buộc, `from_status`, `to_status` bắt buộc, `occurred_at datetime2(3) NOT NULL` theo UTC. Sự kiện `HANDED_OVER → RETURNED` là nguồn dữ liệu của người và thời điểm nhận. |
| Chỉ mục | Giữ chỉ mục lịch theo `(equipment_id, status, start_at)` và unique filtered index theo `equipment_id WHERE status = 'HANDED_OVER'` của #115. Khi commit nhận lại, dòng yêu cầu tự rời chỉ mục lọc. |

Vòng đời gồm `PENDING → APPROVED → HANDED_OVER → RETURNED` và `PENDING → REJECTED`. `RETURNED` và `REJECTED` là trạng thái kết thúc. `SYSUTCDATETIME()` cấp thời điểm nhận tại SQL Server. API trả thời điểm ISO 8601 UTC và giao diện hiển thị theo `Asia/Bangkok`.

## API và quyền

| Điểm vào | Hợp đồng |
|---|---|
| `POST /loan-requests/{id}/return` | Phiên quản lý, header `X-CSRF-Token`, body rỗng. Sau commit trả `200` với yêu cầu đã cập nhật theo DTO của #113–115, gồm `status: "RETURNED"`. Bổ sung `returned_at` và `returned_by` kiểu ID trong phản hồi dành cho quản lý, lấy từ sự kiện nhận lại. |
| `GET /loan-requests`, `GET /loan-requests/{id}` | Tái sử dụng API đọc. Đề xuất danh sách quản lý lọc bằng `?status=HANDED_OVER` theo cơ chế danh sách của #114–115. Chi tiết quản lý dùng để kiểm tra trạng thái và thông tin nhận lại khi tải lại. Thành viên đọc theo `borrower_id = session.user_id` và thấy trạng thái đã trả. Ngoài phạm vi sở hữu trả `404`. |
| `GET /equipment/{id}/availability?from=…&to=…` | Tái sử dụng #112. Tra cứu theo ID thiết bị, trả khoảng trống và múi giờ CLB. Phản hồi chỉ chứa dữ liệu lịch. |
| `POST /loan-requests/{id}/handover` | Tái sử dụng #115. Kiểm tra yêu cầu đang `APPROVED` và thiết bị hiện rảnh dưới khóa thiết bị. |

Kiểm tra phiên, CSRF và quyền quản lý trước khi đọc yêu cầu cho lệnh nhận lại. Dùng lỗi cùng cấu trúc với API nền tảng. Thiếu hoặc hết phiên trả `401`. Phiên thành viên hoặc CSRF không hợp lệ trả `403`, với `CSRF_INVALID` cho lỗi CSRF. ID sai định dạng trả `400`. ID hợp lệ không tồn tại trả `404`. Trạng thái nguồn khác `HANDED_OVER`, kể cả lặp lại sau commit, trả `409 INVALID_TRANSITION`. Lỗi ghi dữ liệu trả lỗi máy chủ theo quy ước API. Danh tính người nhận lấy từ phiên.

## LLD giao dịch và lịch

1. Sau khi kiểm tra quyền, mở giao dịch SQL Server `READ COMMITTED` trên một kết nối. Đọc `equipment_id` của yêu cầu bằng câu lệnh riêng dựa trên tính bất biến của cột này. Nếu không tìm thấy, rollback và trả `404`.
2. Khóa dòng thiết bị theo PK bằng `SELECT … WITH (UPDLOCK, HOLDLOCK)`. Đọc lại yêu cầu theo ID và ID thiết bị bằng `WITH (UPDLOCK, HOLDLOCK)`. Kiểm tra tồn tại và trạng thái từ kết quả dưới khóa. Duyệt, từ chối, giao và nhận lại dùng cùng thứ tự khóa thiết bị rồi yêu cầu.
3. Lấy một giá trị `@returned_at datetime2(3)` từ `SYSUTCDATETIME()`. Các câu lệnh ghi dưới đây chạy trong giao dịch, với tên schema theo cấu hình hiện hành. `@actor_id` được truyền từ phiên đã xác thực.

   ```sql
   UPDATE loan_requests
   SET status = 'RETURNED'
   WHERE id = @request_id
     AND equipment_id = @equipment_id
     AND status = 'HANDED_OVER';

   IF @@ROWCOUNT <> 1
       THROW 51001, 'INVALID_TRANSITION', 1;

   INSERT INTO loan_events
       (request_id, actor_id, from_status, to_status, occurred_at)
   VALUES
       (@request_id, @actor_id, 'HANDED_OVER', 'RETURNED', @returned_at);
   ```

4. Tạo dữ liệu phản hồi từ thay đổi trong giao dịch và chỉ gửi sau khi commit thành công. Mọi lỗi trước commit đi qua xử lý rollback. Nếu client mất phản hồi, giao diện tải lại chi tiết bằng API đọc. Khi trạng thái đã là `RETURNED`, hiển thị kết quả đã lưu. Khi vẫn là `HANDED_OVER`, cho phép xác nhận lại. Hai lệnh nhận đồng thời cho cùng yêu cầu tạo đúng một sự kiện nhận. Lệnh đến sau thấy `RETURNED` và nhận `409`.
5. Lịch đặt tính phần bù của hợp các khoảng `APPROVED` hoặc `HANDED_OVER` trong cửa sổ tra cứu. Điều kiện giao nhau là `start_at < @to AND @from < end_at`. Ngay sau commit, truy vấn mới bỏ qua khoảng của yêu cầu `RETURNED`, giữ các khoảng bận khác và giữ giờ đặt gốc để hiển thị lịch sử yêu cầu. Lịch phản ánh trạng thái hiện hành cho cửa sổ tra cứu.
6. Khi giao chạy song song với nhận lại, lệnh lấy khóa thiết bị trước được xét trước. Nếu giao thấy lượt cũ còn `HANDED_OVER`, trả `409 EQUIPMENT_IN_USE`, lượt mới vẫn `APPROVED`. Nếu nhận lại commit trước khi giao lấy được khóa, giao đọc lại dưới khóa rồi có thể thành công nếu các điều kiện #115 vẫn thỏa. Lệnh duyệt của #114 cũng kiểm tra sau khi lấy khóa, chỉ xét các yêu cầu khác cùng thiết bị có trạng thái `APPROVED` hoặc `HANDED_OVER` và thỏa `existing.start_at < requested.end_at AND requested.start_at < existing.end_at`. Yêu cầu đã trả vì vậy cũng rời tập kiểm tra xung đột.

## Bàn giao BA

Đề xuất điểm vào **Yêu cầu đã giao**, có thao tác **Xác nhận nhận lại** và hộp thoại xác nhận. Prototype dùng dữ liệu tổng hợp, hiển thị tải, danh sách rỗng, lỗi tải, yêu cầu đang xử lý và kết quả đã trả. Sau khi xác nhận, tải lại danh sách. Với lỗi do phiên khác thao tác hoặc mất phản hồi, tải lại chi tiết và hiển thị kết quả từ máy chủ.

| Ca SRS và prototype | Kết quả cần thể hiện |
|---|---|
| Nhận lại hợp lệ | Quản lý nhận lại một lượt đã giao. Một sự kiện có người nhận và giờ nhận do máy chủ cấp. Thành viên tải lại thấy **Đã trả**. |
| Nhận sớm và tra cứu lịch | Lượt A đặt 09:00–11:00 và nhận lại lúc 10:00. Tra cứu 10:00–12:00 thấy 10:00–11:00 trống. Lượt B cùng thiết bị đã duyệt 11:00–12:00 vẫn chiếm lịch. Giờ minh họa theo giờ CLB. |
| Giao lượt kế tiếp | Trong khi A còn được giữ, kể cả quá giờ đặt, giao B nhận `EQUIPMENT_IN_USE`. Sau khi nhận A, xác nhận giao B thành công nếu thiết bị đang rảnh. |
| Quyền và trạng thái | Khách, thành viên gọi thẳng, lỗi CSRF, ID không tồn tại và yêu cầu sai trạng thái nhận đúng lỗi. Thành viên khác truy cập chi tiết nhận `404`. |
| Cạnh tranh và phục hồi | Hai quản lý cùng nhận chỉ có một sự kiện. Mất phản hồi sau commit được xác định qua tải lại. Lỗi ghi sự kiện rollback cả trạng thái. Kiểm thử giao đồng thời với nhận theo cả hai thứ tự lấy khóa. |

## Phụ thuộc và xác minh

- #111 cung cấp phiên, CSRF, vai trò và ID thiết bị vật lý. #112 cung cấp migration yêu cầu và truy vấn lịch. Bản bàn giao báo đã có backend #112 và còn vướng xác minh tích hợp SQL Server. Workspace lượt này chỉ có migration nền tảng.
- #113 cung cấp API đọc và phạm vi sở hữu. #114 cung cấp nhật ký sự kiện, API quản lý và khóa chống duyệt trùng. #115 cung cấp thao tác giao, chỉ mục bảo vệ tình trạng giữ thiết bị và quy tắc giao khi rảnh.
- BA có thể viết SRS và prototype độc lập theo các hợp đồng trên. Trước khi triển khai cần đối chiếu tên cột, kiểu dữ liệu, DTO và bộ lọc danh sách với các bản triển khai #112–115. Kiểm thử giao dịch trên SQL Server với hai kết nối và dữ liệu tổng hợp thuộc bước tích hợp sau khi có các phụ thuộc đó.
