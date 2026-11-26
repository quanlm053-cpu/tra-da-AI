# Thiết kế gửi và theo dõi yêu cầu mượn

Bàn giao BA cho Story #113, task SA #128. Căn cứ vào yêu cầu PM trên Redmine, bản bàn giao SA/BA #112 và lớp phiên, phân quyền, danh mục của #111.

## HLD

Trình duyệt dùng giao diện và API Node.js cùng origin HTTPS qua Caddy. Thành viên chọn ID thiết bị vật lý từ `GET /equipment`, nhập giờ theo `Asia/Bangkok`, gửi yêu cầu và mở danh sách hoặc chi tiết của mình. API dùng phiên máy chủ để xác định người mượn và đọc trạng thái hiện tại từ Microsoft SQL Server. Backend dùng T-SQL tham số hóa. Giao diện có thể điền sẵn thiết bị và giờ từ màn lịch #112. Kết quả tra cứu lịch chỉ là thông tin tại lần đọc. Khi gửi, yêu cầu bắt đầu ở `PENDING`, kể cả khi có lượt khác trùng giờ. Quyết định giữ lịch diễn ra khi quản lý duyệt ở #114.

#113 phụ thuộc vào nền tảng đang có của #111 và migration `loan_requests` do #112 cung cấp. Bản thiết kế và SRS #112 đã bàn giao, còn backend #127 đang triển khai tại thời điểm chuẩn bị. Trước khi triển khai #113, đối chiếu tên bảng, kiểu cột, chỉ mục và đường dẫn với bản #112 đã tích hợp. Dùng lại migration đó. #113 chỉ cần bổ sung chỉ mục danh sách nếu chưa có chỉ mục tương đương. Chức năng gửi và theo dõi dùng danh mục #111 nên BA có thể đặc tả và dựng prototype trước khi API lịch hoàn tất.

## Schema SQL Server

| Bảng | Hợp đồng dữ liệu |
| --- | --- |
| `users`, `sessions`, `equipment` (#111) | Phiên cho biết ID và vai trò hiện hành. `users.id` và `equipment.id` là PK kiểu `int`. `equipment.asset_code` là mã phân biệt thiết bị vật lý cùng tên. |
| `loan_requests` (#112, dùng lại ở #113) | `id int IDENTITY` PK, `equipment_id int` FK tới `equipment.id`, `borrower_id int` FK tới `users.id`. `start_at`, `end_at`, `created_at` kiểu `datetime2(3)` lưu UTC. `created_at` mặc định `SYSUTCDATETIME()`. `status varchar(16)` có CHECK thuộc `PENDING`, `APPROVED`, `REJECTED`, `HANDED_OVER`, `RETURNED`. Các cột đều NOT NULL và CHECK `start_at < end_at`. Người mượn, thiết bị và giờ đặt cố định sau khi tạo. |
| `loan_events` (#114 trở đi) | `id int IDENTITY` PK, `request_id int` FK tới yêu cầu, `actor_id int` FK tới người thao tác, `from_status`, `to_status varchar(16)` có CHECK theo tập trạng thái, `occurred_at datetime2(3)` UTC. Các cột đều NOT NULL. |

Giữ chỉ mục lịch `(equipment_id, status, start_at) INCLUDE (end_at)` của #112. Danh sách #113 dùng chỉ mục `(borrower_id, created_at DESC, id DESC)` theo thứ tự sắp xếp ổn định. Cho phép nhiều hàng có cùng thiết bị và giờ đặt. Từ #115, unique filtered index trên `equipment_id WHERE status = 'HANDED_OVER'` bảo vệ ràng buộc mỗi thiết bị chỉ có một lượt đang giữ thực tế.

## API Story #113

Mọi tuyến dưới đây yêu cầu `MEMBER`. Dùng các đường dẫn cùng origin, định tuyến trong backend và chuyển tiếp qua Caddy cho `/loan-requests` và đường dẫn chi tiết. Dùng `Cache-Control: no-store` cho phản hồi. Các trường JSON theo snake_case.

| Method và path | Đầu vào và kết quả |
| --- | --- |
| `POST /loan-requests` | JSON gồm đúng `equipment_id`, `start_at`, `end_at`. Yêu cầu header `X-CSRF-Token` từ phiên. Trả `201` và đối tượng yêu cầu có `status: "PENDING"`, kèm `Location: /loan-requests/{id}`. |
| `GET /loan-requests` | Trả `200` và mảng đối tượng yêu cầu của thành viên, theo `created_at DESC, id DESC`. Chọn danh sách đầy đủ trong phạm vi #113. Trả `[]` khi chưa có yêu cầu. |
| `GET /loan-requests/{id}` | Trả `200` và đối tượng yêu cầu thuộc thành viên, hoặc cùng phản hồi `404 NOT_FOUND` cho ID ngoài quyền sở hữu và ID chưa tồn tại. |

Ví dụ payload gửi cho thiết bị mẫu vào 09:00–10:00 giờ CLB.

```json
{
  "equipment_id": 1,
  "start_at": "2026-11-16T09:00:00+07:00",
  "end_at": "2026-11-16T10:00:00+07:00"
}
```

Ví dụ đối tượng trả về cho ba tuyến.

```json
{
  "id": 42,
  "equipment_id": 1,
  "start_at": "2026-11-16T02:00:00.000Z",
  "end_at": "2026-11-16T03:00:00.000Z",
  "created_at": "2026-11-15T10:00:00.000Z",
  "status": "PENDING"
}
```

FE tra tên và mã thiết bị theo ID từ danh mục #111. Phản hồi gồm các trường được liệt kê trong ví dụ, đủ để hiển thị trạng thái hiện tại. Người dùng tải lại danh sách hoặc mở lại chi tiết để đọc trạng thái mới. Quản lý truy cập hàng đợi và chi tiết toàn CLB từ #114 theo hợp đồng của Story đó. Khi mở rộng tuyến chung, duy trì nhánh truy vấn theo quyền sở hữu cho `MEMBER`.

| HTTP và `code` | Điều kiện |
| --- | --- |
| `401 AUTH_REQUIRED` | Phiên thiếu, hết hạn hoặc đã thu hồi. |
| `403 FORBIDDEN` | Sai vai trò. |
| `403 CSRF_INVALID` | POST thiếu hoặc sai token CSRF. |
| `400 INVALID_INPUT` | JSON sai, thiếu hoặc thừa trường, ID sai miền hoặc giờ đặt sai. |
| `404 NOT_FOUND` | Thiết bị gửi lên chưa tồn tại, hoặc chi tiết nằm ngoài phạm vi của thành viên. |
| `500 INTERNAL_ERROR` | Lỗi máy chủ hoặc truy vấn bất ngờ. |

Lỗi có dạng `{"code":"NOT_FOUND"}`. Xử lý theo thứ tự phiên, vai trò, CSRF cho POST, kiểm tra dữ liệu, truy cập đối tượng. Giữ lớp phân quyền hiện có của #111 cho cả route động. Giới hạn ID thiết bị và ID yêu cầu ở số nguyên dương trong miền SQL Server `int`. Mốc giờ dùng ISO 8601 với ngày, giờ, phút, giây, offset `Z` hoặc `±HH:mm` và tối đa ba chữ số phần giây như #112. Kiểm tra ngày giờ thực, miền `datetime2(3)` sau đổi sang UTC và `start_at < end_at` sau chuẩn hóa. Cho phép đặt qua ngày. Mọi khoảng có dạng nửa mở `[start, end)`.

## LLD tạo và đọc theo chủ sở hữu

Bind các ID kiểu `Int`, mốc UTC kiểu `DateTime2(3)`. API lấy `@borrower_id` từ phiên và ghi trạng thái cố định. Dùng một INSERT autocommit. FK bảo đảm thiết bị tồn tại tại thời điểm ghi. Nếu INSERT vi phạm FK thiết bị do thiết bị vừa bị xóa hoặc chưa tồn tại, trả `404 NOT_FOUND`. Phân loại lỗi theo ràng buộc cụ thể. Chỉ trả `201` sau khi lệnh hoàn tất thành công. Mỗi POST hợp lệ tạo một yêu cầu riêng. Nếu mất phản hồi sau khi gửi, FE hướng thành viên kiểm tra danh sách trước khi gửi lại.

```sql
INSERT dbo.loan_requests (equipment_id, borrower_id, start_at, end_at, status)
OUTPUT inserted.id, inserted.equipment_id, inserted.start_at,
       inserted.end_at, inserted.created_at, inserted.status
VALUES (@equipment_id, @borrower_id, @start_utc, @end_utc, 'PENDING');

SELECT id, equipment_id, start_at, end_at, created_at, status
FROM dbo.loan_requests
WHERE borrower_id = @borrower_id
ORDER BY created_at DESC, id DESC;

SELECT id, equipment_id, start_at, end_at, created_at, status
FROM dbo.loan_requests
WHERE id = @request_id AND borrower_id = @borrower_id;
```

`dbo` minh họa schema. Store dùng tên schema đã được nền tảng kiểm tra. Với chi tiết, dùng trực tiếp truy vấn có điều kiện sở hữu. Kết quả rỗng luôn đi qua cùng nhánh `404`. Giao diện xử lý mã lỗi khi người dùng mở URL trực tiếp, còn backend thực thi điều kiện sở hữu trên mỗi lần đọc.

## LLD chuyển trạng thái và chống duyệt trùng cho #114–116

| Lệnh quản lý | Chuyển trạng thái | Điều kiện trong giao dịch |
| --- | --- | --- |
| `approve` (#114) | `PENDING → APPROVED` | Không có lượt khác cùng thiết bị trùng giờ với trạng thái `APPROVED` hoặc `HANDED_OVER`. Xung đột trả `409 SCHEDULE_CONFLICT` và giữ `PENDING`. |
| `reject` (#114) | `PENDING → REJECTED` | Đúng trạng thái nguồn. |
| `handover` (#115) | `APPROVED → HANDED_OVER` | Không có lượt khác cùng thiết bị còn `HANDED_OVER`, kể cả quá giờ. Xung đột trả `409 EQUIPMENT_IN_USE` và giữ `APPROVED`. |
| `return` (#116) | `HANDED_OVER → RETURNED` | Đúng trạng thái nguồn. Khi commit, lượt trả thôi chiếm lịch và thôi giữ thiết bị. |

1. Kiểm tra phiên, `MANAGER` và CSRF trước khi tra yêu cầu. Trên cùng kết nối, mở giao dịch `READ COMMITTED`. Đọc `equipment_id` bất biến theo ID yêu cầu với một câu đọc thông thường. Nếu thiếu yêu cầu, rollback và trả `404`.
2. Khóa dòng thiết bị bằng `SELECT id FROM dbo.equipment WITH (UPDLOCK, HOLDLOCK) WHERE id = @equipment_id`. Sau đó đọc và khóa dòng yêu cầu với `UPDLOCK, HOLDLOCK`, xác nhận nó còn tồn tại và có đúng thiết bị cùng trạng thái nguồn. Sai trạng thái nguồn trả `409 INVALID_TRANSITION`, kể cả khi lệnh trước đó đã thành công. Mọi lệnh đổi trạng thái dùng thứ tự khóa thiết bị rồi yêu cầu.
3. Với duyệt, sau khi lấy khóa thiết bị, chạy câu lệnh riêng kiểm tra `EXISTS` trên `loan_requests` với điều kiện bên dưới. Khoảng sát biên được duyệt. Lượt duyệt thứ hai trên cùng thiết bị chờ khóa rồi đọc trạng thái đã commit của lượt đầu. Nếu lượt đầu rollback, lượt thứ hai xét theo dữ liệu hiện hành. Với giao thiết bị, kiểm tra có lượt khác đang giữ bằng cùng khóa thiết bị, trên toàn bộ giờ đặt.
4. Cập nhật có điều kiện theo ID và trạng thái nguồn, xác nhận đúng một hàng thay đổi. Ghi sự kiện cùng giao dịch, lấy actor từ phiên và thời gian UTC từ `SYSUTCDATETIME()`. Trả `200` cùng đối tượng đã cập nhật sau commit. Lỗi hoặc xung đột rollback và trả lỗi tương ứng. Nếu mất phản hồi sau commit, đọc lại trạng thái trước khi thao tác tiếp.

```sql
SELECT 1
FROM dbo.loan_requests
WHERE equipment_id = @equipment_id
  AND id <> @request_id
  AND status IN ('APPROVED', 'HANDED_OVER')
  AND start_at < @request_end_utc
  AND end_at > @request_start_utc;
```

## Bàn giao BA

| Ca SRS và prototype #113 | Kết quả cần thể hiện |
| --- | --- |
| Chọn thiết bị theo mã tài sản và gửi 09:00–10:00 | Hiển thị giờ CLB có nhãn, xác nhận đã gửi, thêm yêu cầu vào danh sách với nhãn Chờ duyệt. |
| Giờ bằng nhau, đảo chiều hoặc thiếu offset khi gọi API | Báo lỗi trường giờ trên form khi phù hợp. API trả `400` và không có hàng mới. |
| Gửi hai lượt trùng nhau trên cùng thiết bị | Cả hai nhận `201`, ID khác nhau và cùng `PENDING`. Lịch #112 vẫn trống nếu chưa có lượt chiếm lịch. Dùng hai tài khoản thành viên tổng hợp để kiểm tra quyền. |
| Mở danh sách và tải lại chi tiết của mình | Hiển thị đúng thiết bị, giờ CLB và trạng thái hiện tại. Prototype dùng fixture tổng hợp cho các trạng thái Chờ duyệt, Đã duyệt, Đã từ chối, Đã giao, Đã trả. |
| Mở URL chi tiết của thành viên khác và thử ID không tồn tại | Hai trường hợp cùng `404 NOT_FOUND`. Danh sách của mỗi thành viên chỉ chứa yêu cầu của mình và phản hồi lỗi không lộ dữ liệu đối tượng. |
| Danh sách mới, hết phiên, thiết bị thiếu, truy vấn lỗi hoặc mất phản hồi khi gửi | Phân biệt tải, rỗng và lỗi. Khi hết phiên, yêu cầu đăng nhập. Khi mất phản hồi POST, hướng dẫn kiểm tra danh sách trước khi gửi lại. |

Ở bước tích hợp #113, kiểm tra bảo vệ POST bằng CSRF, vai trò, dữ liệu giả mạo `borrower_id` hoặc `status`, và quyền đọc trực tiếp. Ở #114, dùng hai kết nối SQL Server riêng để kiểm tra duyệt đồng thời hai lượt trùng, hai lượt sát biên, hai thiết bị khác nhau và rollback khi ghi sự kiện lỗi. Ở #115–116, kiểm tra giao khi lượt trước quá giờ chưa trả và giao lại sau khi lượt trước đã trả.
