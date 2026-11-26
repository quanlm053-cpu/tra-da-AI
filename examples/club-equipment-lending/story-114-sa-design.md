# Thiết kế duyệt và từ chối yêu cầu mượn

Bàn giao BA cho Story #114, task SA #130. Nguồn đối chiếu gồm tiêu chí Redmine #114/#130, bàn giao #111–113 trên MCP Lending và mã nền tảng #111 trong workspace.

## HLD

Trình duyệt gọi API cùng origin qua HTTPS. API kiểm tra phiên, vai trò và CSRF trước khi gọi tầng nghiệp vụ. Microsoft SQL Server lưu yêu cầu, lịch và sự kiện đổi trạng thái. Mỗi thiết bị vật lý có một ID và là đơn vị khóa khi đổi trạng thái. Cơ chế này có hiệu lực giữa nhiều tiến trình API cùng dùng một cơ sở dữ liệu.

Quản lý xem hàng đợi toàn CLB và quyết định từng yêu cầu. Duyệt thành công làm khoảng đặt chiếm lịch ngay sau commit. Từ chối kết thúc yêu cầu đang chờ. Khi có lịch trùng, API báo xung đột và giữ yêu cầu ở trạng thái chờ để quản lý xem lại hoặc từ chối. Thành viên thấy trạng thái đã commit qua API của #113. API lịch #112 tiếp tục chỉ cung cấp dữ liệu lịch theo thiết bị.

| Phụ thuộc | Hợp đồng tích hợp |
|---|---|
| #111, đã bàn giao | Phiên phía máy chủ, `MANAGER` và `MEMBER`, `X-CSRF-Token`, `users.id` và `equipment.id` kiểu `int`. Khi triển khai, nối các đường dẫn động vào lớp bảo vệ của API và định tuyến `/loan-requests` cùng các đường dẫn con qua Caddy. |
| #112, backend đang tích hợp | Dùng chung migration `loan_requests`, trạng thái chiếm lịch và quy ước UTC. Đối chiếu tên cột, kiểu khóa yêu cầu và chỉ mục với migration thực tế trước khi viết migration #114. |
| #113, đã có bàn giao thiết kế | Tạo yêu cầu `PENDING` kể cả khi giờ trùng. Thiết bị, người mượn và giờ đặt cố định sau khi tạo. Giữ phạm vi sở hữu và định dạng phản hồi API của thành viên. |
| #115–116 | Dùng cùng thứ tự khóa để giao, nhận lại và ghi sự kiện. #115 kiểm tra thiết bị còn đang được giữ, #116 chuyển sang `RETURNED` để giải phóng phần lịch còn lại. |

Thiết kế và prototype có thể dùng fixture tổng hợp khi #112–113 đang tích hợp. Kiểm thử đầu cuối cần migration và API tạo yêu cầu của hai Story trước.

## Schema

| Bảng | Cột và ràng buộc |
|---|---|
| `equipment`, `users` | Dùng PK hiện có của #111. Khóa dòng thiết bị theo PK. |
| `loan_requests` | Dùng bảng #112 với `id` PK, `equipment_id` và `borrower_id` FK bắt buộc, `start_at`, `end_at`, `created_at` kiểu `datetime2(3)` UTC, `CHECK (start_at < end_at)`. `status` bắt buộc và chỉ nhận `PENDING`, `APPROVED`, `REJECTED`, `HANDED_OVER`, `RETURNED`. |
| `loan_events` | Thêm ở #114. `id bigint IDENTITY` PK, `request_id` FK cùng kiểu với PK yêu cầu, `actor_id int` FK tới `users(id)`, `from_status` và `to_status varchar(16)`, `occurred_at datetime2(3)` UTC lấy từ `SYSUTCDATETIME()`. Các cột bắt buộc. CHECK cặp trạng thái theo bảng vòng đời dưới đây. Ghi thêm một dòng cho mỗi lần chuyển thành công. |

Dùng chỉ mục lịch của #112 theo `(equipment_id, status, start_at)` với `end_at` trong INCLUDE nếu cần. Đề xuất `(status, created_at, id)` cho hàng đợi. Tra cứu sự kiện theo `(request_id, id)`. Ràng buộc khoảng thời gian và tập trạng thái nằm ở schema. Quy tắc giao nhau giữa các dòng nằm trong giao dịch duyệt.

## API và quyền

| API | Quyền và thành công |
|---|---|
| `GET /loan-requests` | Với `MANAGER`, trả `200` và mảng yêu cầu `PENDING` toàn CLB theo `created_at ASC, id ASC`, mảng rỗng khi hết yêu cầu. Với `MEMBER`, giữ danh sách yêu cầu của chính mình theo #113. |
| `GET /loan-requests/{id}` | `MANAGER` xem chi tiết toàn CLB để đối chiếu sau thao tác. `MEMBER` xem chi tiết theo điều kiện `borrower_id = session.user.id`. |
| `POST /loan-requests/{id}/approve` | Chỉ `MANAGER`. Trả `200` với yêu cầu đã chuyển sang `APPROVED`. |
| `POST /loan-requests/{id}/reject` | Chỉ `MANAGER`. Trả `200` với yêu cầu đã chuyển sang `REJECTED`. |

Bản ghi dùng các trường `id`, `equipment_id`, `borrower_id`, `start_at`, `end_at`, `created_at`, `status`. Phản hồi hàng đợi và chi tiết cho quản lý bổ sung `equipment_asset_code`, `equipment_name`, `borrower_username` từ JOIN để quản lý nhận diện thiết bị và người gửi. Chọn danh sách đầy đủ và thứ tự cũ trước cho phạm vi hiện tại. Các lệnh POST gửi body rỗng, dùng cookie phiên và header `X-CSRF-Token`. Lấy người thao tác từ phiên, lấy hành động từ route và lấy thiết bị, giờ đặt, trạng thái nguồn từ SQL Server. Thời điểm trả về là ISO 8601 UTC có hậu tố `Z`. Giao diện hiển thị theo `Asia/Bangkok` có nhãn múi giờ.

Thứ tự xử lý ở route ghi là phiên còn hiệu lực, vai trò, CSRF, cú pháp ID, đối tượng và trạng thái trong giao dịch. Thực hiện kiểm tra vai trò ngay tại API dù giao diện đã ẩn nút. Dùng hợp đồng lỗi hiện hành `{"code":"..."}`.

| HTTP | Code | Điều kiện |
|---|---|---|
| 401 | `AUTH_REQUIRED` | Thiếu phiên, phiên hết hạn hoặc đã thu hồi. |
| 403 | `FORBIDDEN`, `CSRF_INVALID` | Sai vai trò cho lệnh ghi hoặc CSRF sai/thiếu tương ứng. |
| 400 | `INVALID_INPUT` | ID sai cú pháp hoặc ngoài miền kiểu khóa. |
| 404 | `NOT_FOUND` | ID hợp lệ nhưng thiếu yêu cầu, hoặc chi tiết nằm ngoài sở hữu của thành viên. |
| 409 | `INVALID_TRANSITION` | Yêu cầu hiện tại thiếu trạng thái nguồn hợp lệ, kể cả lệnh lặp sau commit. |
| 409 | `SCHEDULE_CONFLICT` | Duyệt gặp khoảng chiếm lịch giao nhau trên cùng thiết bị. |
| 500 | `INTERNAL_ERROR` | Lỗi SQL hoặc lỗi hệ thống. Giao diện tải lại chi tiết trước khi cho thử lại nếu kết quả lệnh chưa rõ. |

## LLD giao dịch và vòng đời

| Lệnh | Chuyển trạng thái | Điều kiện bổ sung |
|---|---|---|
| Duyệt #114 | `PENDING → APPROVED` | Kiểm tra giao khoảng sau khi khóa thiết bị. |
| Từ chối #114 | `PENDING → REJECTED` | Kiểm tra trạng thái nguồn, bỏ qua kiểm tra giao khoảng. |
| Giao #115 | `APPROVED → HANDED_OVER` | Kiểm tra tình trạng giữ thiết bị thực tế dưới cùng khóa. |
| Nhận lại #116 | `HANDED_OVER → RETURNED` | Sau commit, lượt này rời tập chiếm lịch. |

`REJECTED` và `RETURNED` là trạng thái cuối. Mọi lệnh chuyển trạng thái giữ thứ tự khóa thiết bị rồi yêu cầu. Tầng ghi của API dùng một giao dịch và một kết nối SQL Server cho toàn bộ các bước. T-SQL dưới đây là thiết kế, tên schema và kiểu tham số lấy từ migration; bind `@request_id`, `@actor_id` và `@target` từ dữ liệu đã kiểm tra ở API. `@target` nhận `APPROVED` hoặc `REJECTED` theo route.

```sql
SET XACT_ABORT ON;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @equipment_id int, @locked_equipment_id int;
    DECLARE @status varchar(16), @start_at datetime2(3), @end_at datetime2(3);

    -- Tra cứu khóa định tuyến bất biến trước khi lấy khóa cập nhật.
    SELECT @equipment_id = equipment_id
    FROM dbo.loan_requests
    WHERE id = @request_id;
    IF @equipment_id IS NULL THROW 51040, 'NOT_FOUND', 1;

    SELECT @locked_equipment_id = id
    FROM dbo.equipment WITH (UPDLOCK, HOLDLOCK)
    WHERE id = @equipment_id;
    IF @locked_equipment_id IS NULL THROW 51050, 'INTEGRITY_ERROR', 1;

    SELECT @status = status, @start_at = start_at, @end_at = end_at
    FROM dbo.loan_requests WITH (UPDLOCK)
    WHERE id = @request_id AND equipment_id = @locked_equipment_id;
    IF @status IS NULL THROW 51040, 'NOT_FOUND', 1;
    IF @status <> 'PENDING' THROW 51041, 'INVALID_TRANSITION', 1;

    IF @target = 'APPROVED' AND EXISTS (
        SELECT 1
        FROM dbo.loan_requests
        WHERE equipment_id = @locked_equipment_id
          AND id <> @request_id
          AND status IN ('APPROVED', 'HANDED_OVER')
          AND start_at < @end_at
          AND @start_at < end_at
    ) THROW 51042, 'SCHEDULE_CONFLICT', 1;

    UPDATE dbo.loan_requests
    SET status = @target
    WHERE id = @request_id AND status = 'PENDING';
    IF @@ROWCOUNT <> 1 THROW 51041, 'INVALID_TRANSITION', 1;

    INSERT dbo.loan_events (request_id, actor_id, from_status, to_status, occurred_at)
    VALUES (@request_id, @actor_id, @status, @target, SYSUTCDATETIME());

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
```

Tầng API ánh xạ số lỗi nghiệp vụ sang HTTP và trả bản ghi của lần cập nhật sau khi SQL xác nhận commit. Lấy ảnh bản ghi trong giao dịch để lần chuyển tiếp đồng thời ở #115–116 không thay thế dữ liệu phản hồi của lệnh vừa thực hiện. Khi ghi sự kiện thất bại, rollback cả cập nhật yêu cầu. Khi mất kết nối hoặc hết thời gian chờ, đọc lại chi tiết để xác định trạng thái bền vững. Lỗi khóa và lỗi hạ tầng dùng nhánh lỗi hệ thống.

Lượt duyệt thứ hai trên cùng thiết bị chờ lượt đầu giải phóng khóa. Truy vấn giao khoảng chạy ở câu lệnh riêng sau khi lấy khóa. Với READ COMMITTED dùng khóa đọc hoặc READ_COMMITTED_SNAPSHOT, câu lệnh này thấy kết quả đã commit của lượt trước. Nếu lượt trước rollback, lượt sau xét dữ liệu hiện hành. Mọi đường ghi làm thay đổi tập chiếm lịch phải tuân thủ cùng giao thức. Tạo `PENDING` có thể chạy đồng thời vì trạng thái đó ở ngoài tập chiếm lịch. Khoảng nửa mở `[start_at, end_at)` cho phép cùng thiết bị dùng hai khoảng sát biên. Điều kiện `equipment_id` cho phép hai thiết bị duyệt cùng giờ.

## Bàn giao SRS, prototype và nghiệm thu

| Ca | Kết quả BA cần mô tả |
|---|---|
| Hàng đợi | Có tải, rỗng, lỗi và thử lại. Hiện mã thiết bị vật lý, người gửi, giờ theo múi giờ CLB và hai hành động cho yêu cầu đang chờ. |
| Duyệt hoặc từ chối thành công | Chờ phản hồi rồi bỏ dòng khỏi hàng đợi. Chi tiết thành viên và lần tra cứu lịch mới phản ánh trạng thái đã commit. |
| Hai yêu cầu trùng giờ | Một lượt nhận `200`, một lượt nhận `409 SCHEDULE_CONFLICT`. Dòng bị xung đột vẫn chờ, hiển thị thông báo và cho phép từ chối sau khi cập nhật hàng đợi. |
| Hai yêu cầu sát biên hoặc khác thiết bị | Cả hai có thể được duyệt. Ví dụ giờ CLB 09:00–10:00 và 10:00–11:00 trên cùng thiết bị, hoặc cùng 09:00–10:00 trên hai ID vật lý. |
| Duyệt và từ chối cùng một yêu cầu | Một lần thành công, lần còn lại nhận `INVALID_TRANSITION`. Làm mới trạng thái trước khi cho thao tác tiếp. |
| Truy cập trực tiếp | Khách nhận 401. Thành viên gọi lệnh quản lý với CSRF hợp lệ nhận 403. Quản lý gửi lệnh thiếu CSRF nhận 403. |

Prototype mô phỏng phản hồi API bằng dữ liệu tổng hợp. Khi tích hợp, chạy ca đồng thời trên SQL Server với hai kết nối và hai phiên quản lý, đồng bộ thời điểm gửi lệnh và kiểm tra cả HTTP lẫn dữ liệu. Với ca trùng, xác nhận một yêu cầu `APPROVED`, một `PENDING` và đúng một sự kiện chuyển trạng thái. Kiểm tra thêm rollback khi chèn sự kiện lỗi, ca cạnh tranh duyệt/từ chối và lịch #112 sau khi commit. Tài liệu này đặc tả thiết kế. Việc chạy T-SQL và xác minh giao dịch thuộc bước tích hợp.
