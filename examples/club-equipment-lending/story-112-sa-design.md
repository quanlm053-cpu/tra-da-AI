# Thiết kế lịch trống thiết bị

Bàn giao BA cho Story #112, task SA #125. Căn cứ vào Redmine #112 và #125, kế hoạch #111–116 và các bàn giao #111 trong MCP Lending. Schema và đường dẫn hiện hữu được đối chiếu với mã nguồn trong workspace.

## HLD

Trình duyệt dùng giao diện và API Node.js qua cùng origin HTTPS do Caddy phục vụ. Thành viên đăng nhập bằng phiên máy chủ của #111, chọn một dòng từ `GET /equipment` theo ID thiết bị vật lý và gửi khoảng tra cứu đến API lịch. Quản lý dùng cùng API tra cứu. Backend đọc giờ đặt từ Microsoft SQL Server bằng T-SQL có tham số, tính phần lịch trống và trả các mốc UTC. Giao diện chuyển cả giờ nhập lẫn giờ hiển thị theo múi giờ CLB `Asia/Bangkok`, ghi rõ múi giờ cạnh bộ chọn và kết quả, kể cả khi trình duyệt dùng múi giờ khác.

Lịch phản ánh các giờ đặt đang có hiệu lực tại lần đọc. Trạng thái giữ thiết bị thực tế được kiểm tra riêng khi giao ở #115. Khi đổi thiết bị hoặc khoảng tra cứu, giao diện bỏ kết quả cũ và chỉ hiển thị phản hồi tương ứng lựa chọn hiện tại, kể cả khi phản hồi về sai thứ tự.

### Phụ thuộc và thứ tự triển khai

- #111 cung cấp `users`, `sessions`, `equipment`, cookie phiên và lớp kiểm tra quyền. Hai thiết bị cùng tên vẫn có ID và mã tài sản riêng.
- #112 bổ sung schema `loan_requests` để đọc lịch ngay trong Story này. Demo/test có thể nạp trực tiếp fixture tổng hợp để kiểm tra đủ trạng thái. #113 dùng lại bảng để tạo yêu cầu và theo dõi trạng thái. #114 bổ sung sự kiện và lệnh duyệt/từ chối. #115 bổ sung giao và ràng buộc giữ thiết bị. #116 bổ sung nhận lại.
- Migration #112 chạy sau `001-foundation.sql`, trước khi mở API lịch. Dùng cơ chế giao dịch migration và schema đã kiểm tra của #111. Giữ đường dẫn và định dạng danh mục hiện hành. Caddy bổ sung mẫu `/equipment/*/availability` vào nhóm API. Backend bổ sung định tuyến theo mẫu method/path trong `createApp`, dùng cùng luồng xác thực với route tĩnh và chuyển query đã parse cho handler.

## Schema SQL Server

| Bảng | Cột và ràng buộc |
| --- | --- |
| `equipment` (#111) | `id int IDENTITY` PK, `asset_code varchar(64)` UNIQUE, `name nvarchar(255)`. |
| `loan_requests` (#112) | `id int IDENTITY` PK, `equipment_id int` FK tới `equipment.id`, `borrower_id int` FK tới `users.id`, `start_at`, `end_at`, `created_at datetime2(3)` UTC. `status varchar(16)` có CHECK giới hạn ở `PENDING`, `APPROVED`, `REJECTED`, `HANDED_OVER`, `RETURNED`. Các cột đều NOT NULL, CHECK `start_at < end_at`, mặc định `created_at` là `SYSUTCDATETIME()`. Người mượn, thiết bị và giờ đặt cố định sau khi tạo. |
| `loan_events` (#114) | `id int IDENTITY` PK, `request_id int` FK tới `loan_requests.id`, `actor_id int` FK tới `users.id`, `from_status`, `to_status varchar(16)` có CHECK theo tập trạng thái, `occurred_at datetime2(3)` UTC. Các cột đều NOT NULL. |

- #112 tạo chỉ mục `(equipment_id, status, start_at) INCLUDE (end_at)` để lọc lịch và dùng lại khi duyệt.
- #113 thêm chỉ mục `(borrower_id, created_at)` cho danh sách của thành viên. #115 thêm unique filtered index trên `(equipment_id) WHERE status = 'HANDED_OVER'` để bảo vệ ràng buộc một lượt đang giữ thiết bị.

## API lịch #112

`GET /equipment/{id}/availability?from=…&to=…` yêu cầu phiên hợp lệ của `MEMBER` hoặc `MANAGER`. ID là số nguyên dương trong miền `int` SQL Server. Mỗi tham số `from` và `to` xuất hiện đúng một lần, dùng ISO 8601 ghi ngày, giờ, phút, giây và múi giờ `Z` hoặc offset `±HH:mm`, với tối đa ba chữ số phần giây. Khi gửi offset dương, mã hóa dấu cộng thành `%2B`. Kiểm tra ngày giờ hợp lệ, miền `datetime2(3)` sau khi đổi sang UTC và điều kiện `from < to`. Cửa sổ có thể qua ngày, cho phép tra cứu theo khoảng đã chọn.

Ví dụ phản hồi `200` với cửa sổ 09:00–12:00 giờ CLB và một khoảng bận 10:00–11:00:

```json
{
  "equipment_id": 1,
  "timezone": "Asia/Bangkok",
  "as_of": "2026-11-15T02:00:00.000Z",
  "available": [
    { "start_at": "2026-11-16T02:00:00.000Z", "end_at": "2026-11-16T03:00:00.000Z" },
    { "start_at": "2026-11-16T04:00:00.000Z", "end_at": "2026-11-16T05:00:00.000Z" }
  ]
}
```

`as_of` là giờ UTC do máy chủ ghi sau khi đọc thành công. `available` sắp theo giờ bắt đầu. Lịch bận toàn bộ trả mảng rỗng. Lịch trống toàn bộ trả đúng một khoảng bằng cửa sổ. Phản hồi dùng `Cache-Control: no-store` và chỉ tuần tự hóa các trường trong hợp đồng. Dữ liệu lịch không chứa tên, ID người mượn, ID yêu cầu hay chi tiết yêu cầu.

Lỗi dùng JSON `{"code":"…"}`. Thiếu phiên hoặc phiên hết hạn trả `401 AUTH_REQUIRED`. Phiên có vai trò ngoài tập cho phép trả `403 FORBIDDEN`. Sau kiểm tra phiên và vai trò, ID hoặc khoảng sai trả `400 INVALID_INPUT`, thiết bị hợp lệ về định dạng nhưng không tồn tại trả `404 NOT_FOUND`. Lỗi truy vấn trả `500 INTERNAL_ERROR`. GET chỉ đọc và dùng cơ chế kiểm tra phiên hiện hành.

## LLD tính lịch trống

Mọi khoảng là nửa mở `[start, end)`. Truy vấn đọc thiết bị và khoảng bận trong một câu lệnh. `HOLDLOCK` trên hai bảng giữ phạm vi đọc nhất quán trong câu lệnh autocommit, kể cả khi một lệnh đổi trạng thái chạy đồng thời. Các tên bảng dưới đây minh họa schema mặc định. Store dùng schema cấu hình theo quy tắc kiểm tra định danh của #111.

```sql
SELECT e.id AS equipment_id, r.start_at, r.end_at
FROM dbo.equipment AS e WITH (HOLDLOCK)
LEFT JOIN dbo.loan_requests AS r WITH (HOLDLOCK)
    ON r.equipment_id = e.id
    AND r.status IN ('APPROVED', 'HANDED_OVER')
    AND r.start_at < @to_utc
    AND r.end_at > @from_utc
WHERE e.id = @equipment_id
ORDER BY r.start_at, r.end_at;
```

Bind `@equipment_id` kiểu `Int`, hai mốc kiểu `DateTime2(3)` với quy ước UTC nhất quán ở driver. Không có dòng nghĩa là thiết bị không tồn tại. Dòng có hai mốc NULL nghĩa là thiết bị tồn tại và toàn bộ cửa sổ trống. Với các dòng có mốc giờ, cắt từng khoảng bận theo cửa sổ. Đặt con trỏ tại `from`, duyệt theo thứ tự bắt đầu. Nếu đầu khoảng bận lớn hơn con trỏ, thêm phần trống từ con trỏ tới đầu khoảng bận. Dịch con trỏ tới giá trị lớn hơn giữa vị trí hiện tại và cuối khoảng bận. Cuối vòng lặp, thêm phần từ con trỏ tới `to` nếu con trỏ còn nhỏ hơn `to`. Cách này gộp cả khoảng bận giao nhau và nối tiếp, giữ các phần trống có độ dài dương. Ba trạng thái `PENDING`, `REJECTED`, `RETURNED` bị loại ngay trong truy vấn.

## LLD quyền và chuyển trạng thái cho các Story phụ thuộc

API lấy vai trò và ID người dùng từ phiên trên máy chủ. Lệnh ghi kiểm tra `X-CSRF-Token` qua lớp hiện hữu. Thành viên tạo yêu cầu thông qua `POST /loan-requests` với `equipment_id`, `start_at`, `end_at`. API gán người mượn từ phiên và lưu `PENDING` với `201`, kể cả khi trùng giờ. `GET /loan-requests` và `GET /loan-requests/{id}` của thành viên luôn lọc theo `borrower_id` từ phiên và trả `404` cho ID ngoài phạm vi. Quản lý được xem hàng đợi và chi tiết toàn CLB.

`POST /loan-requests/{id}/{action}` yêu cầu `MANAGER` trước khi truy vấn đối tượng và trả `200` cùng yêu cầu đã cập nhật sau commit. Dùng `403 FORBIDDEN` khi sai vai trò, `403 CSRF_INVALID` khi kiểm tra CSRF thất bại và `404 NOT_FOUND` khi yêu cầu không tồn tại.

| Lệnh | Trạng thái nguồn → đích | Điều kiện bổ sung |
| --- | --- | --- |
| `approve` (#114) | `PENDING → APPROVED` | Không có lượt khác của thiết bị giao giờ trong `APPROVED` hoặc `HANDED_OVER`. |
| `reject` (#114) | `PENDING → REJECTED` | Trạng thái nguồn hợp lệ. |
| `handover` (#115) | `APPROVED → HANDED_OVER` | Không có lượt khác của thiết bị còn `HANDED_OVER`, kể cả quá giờ đặt. |
| `return` (#116) | `HANDED_OVER → RETURNED` | Giải phóng phần lịch bận của yêu cầu và trạng thái giữ thiết bị khi commit. |

Mỗi lệnh mở một giao dịch `READ COMMITTED`. Đọc ID thiết bị bất biến của yêu cầu, rồi dùng `SELECT id FROM dbo.equipment WITH (UPDLOCK, HOLDLOCK) WHERE id = @equipment_id` lấy khóa theo thiết bị. Sau đó đọc và khóa yêu cầu bằng `UPDLOCK, HOLDLOCK`, kiểm tra trạng thái nguồn dưới khóa. Tất cả lệnh đổi trạng thái tuân theo thứ tự thiết bị rồi yêu cầu, kể cả khi chạy trên nhiều tiến trình API.

Sau khi lấy khóa, lệnh duyệt chạy một câu lệnh riêng với điều kiện `equipment_id = @equipment_id AND id <> @request_id AND status IN ('APPROVED', 'HANDED_OVER') AND start_at < @request_end AND end_at > @request_start`. Lượt duyệt thứ hai trên cùng thiết bị đợi giao dịch thứ nhất kết thúc rồi đọc kết quả đã commit. Nếu có giao nhau, rollback và trả `409 SCHEDULE_CONFLICT`, giữ yêu cầu ở `PENDING`. Hai lượt sát biên hoặc thuộc hai thiết bị khác nhau đều có thể duyệt. Lệnh giao kiểm tra dưới cùng khóa xem thiết bị còn lượt `HANDED_OVER` khác hay không. Nếu còn, rollback và trả `409 EQUIPMENT_IN_USE`, giữ yêu cầu ở `APPROVED`.

Nguồn sai trả `409 INVALID_TRANSITION`, kể cả khi gọi lại lệnh đã thành công. Cập nhật trạng thái và ghi sự kiện cùng giao dịch, lấy người thao tác từ phiên và giờ UTC từ `SYSUTCDATETIME()`. Bất kỳ lỗi ghi nào cũng rollback cả hai. Khi mất phản hồi sau commit, giao diện đọc lại trạng thái trước khi cho thao tác tiếp. Một lần tra cứu có thể hết hiệu lực khi giao dịch khác commit, vì vậy quyết định duyệt luôn kiểm tra lại trong giao dịch.

## Bàn giao SRS và prototype

| Ca kiểm tra Story #112 | Kết quả mong đợi |
| --- | --- |
| Chọn hai máy chiếu cùng tên, mã `DEMO-01` và `DEMO-02` | Lịch theo đúng ID thiết bị. Fixture chỉ đặt trên `DEMO-01` thì `DEMO-02` trống toàn cửa sổ. |
| Tra cứu 09:00–13:00 giờ CLB, có lượt đã duyệt 08:30–10:00 và đã giao 10:00–11:00 | Hai lượt sát biên chiếm phần liên tục 09:00–11:00, chỉ còn 11:00–13:00. Khoảng kết thúc đúng 09:00 hoặc bắt đầu đúng 13:00 nằm ngoài cửa sổ. |
| Thêm lượt chờ, từ chối và đã trả trong 11:00–13:00 | 11:00–13:00 vẫn trống. Dùng fixture tổng hợp để độc lập với #113–116. |
| Tra cứu 09:00–11:00 với fixture trên | Báo không có khung giờ trống. Phân biệt với lỗi máy chủ hoặc danh mục không có thiết bị. |
| Trình duyệt ở múi giờ khác, đổi thiết bị khi phản hồi cũ còn đang tải | Nhãn và giờ vẫn theo `Asia/Bangkok`. Kết quả luôn khớp thiết bị và cửa sổ mới nhất. |
| Gửi mốc thiếu offset, ngày sai, khoảng rỗng hoặc đảo chiều | Giao diện báo lỗi nhập. Gọi API trực tiếp với phiên hợp lệ nhận `400`. |
| Mở màn lịch khi chưa có phiên, để phiên hết hạn hoặc tra cứu ID không tồn tại | Màn lịch yêu cầu đăng nhập khi nhận `401`. Với phiên hợp lệ và ID không tồn tại, hiển thị thông báo thiết bị không còn khả dụng. |
| Kiểm tra JSON và màn lịch bằng cả hai vai trò | Chỉ thấy giờ trống và ngữ cảnh tra cứu. Không lộ danh tính người mượn. |

BA dùng các ca trên để viết SRS và dựng prototype với bộ chọn thiết bị, giờ bắt đầu/kết thúc, nhãn múi giờ và các trạng thái tải, trống, lỗi, hết phiên và thử lại. Hợp đồng duyệt, giao và nhận lại được dùng khi đặc tả các Story tương ứng.
