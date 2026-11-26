# Hạ độ dài tối thiểu của mật khẩu đăng ký xuống 8 ký tự

Bàn giao BA task #178, Story #176, task SA #177. Căn cứ gồm Redmine #176–177, bàn giao #166 qua MCP Lending và mã nguồn hiện hành. Bàn giao #166 xác nhận SQL Server đã phân xử hai lượt đăng ký đồng thời và middleware đã chặn thành viên gọi API quản lý. Bản sửa #175 đã kiểm tra UTF-8 lỗi và surrogate đứng lẻ tại API.

## HLD

Trình duyệt và API cùng origin HTTPS qua Caddy. Từ màn đăng nhập, khách mở biểu mẫu đăng ký, nhập tên và mật khẩu rồi gửi JSON. Backend Node.js kiểm tra đầu vào, băm Argon2id và ghi tài khoản thành viên vào Microsoft SQL Server bằng T-SQL. Sau `201`, giao diện xác nhận tạo tài khoản và cho khách quay về đăng nhập với tên đã điền sẵn, ô mật khẩu trống. Khách tự đăng nhập để nhận phiên rồi mở danh mục thiết bị.

Thay ngưỡng từ 12 xuống 8 tại luồng đăng ký. Dùng kiểm tra Unicode của backend làm chuẩn cho giao diện. Luồng đăng nhập tiếp tục xác minh mật khẩu và hash hiện có theo #111, áp dụng bộ kiểm tra đầu vào riêng của đăng nhập. Thay đổi này có thể triển khai backend trước frontend để giao diện mới hoạt động với API đã chấp nhận 8 điểm mã.

## LLD kiểm tra dữ liệu và lưu tài khoản

1. Kiểm tra origin, hạn mức riêng của đăng ký và JSON UTF-8 hợp lệ với giới hạn body hiện có là 8.192 byte. Chấp nhận đối tượng có đúng `username` và `password`. Tên gốc tối đa 128 đơn vị UTF-16. Chuẩn hóa bằng `trim().toLowerCase()`, kiểm tra tên chuẩn 3–64 ký tự theo định dạng #166, bắt đầu bằng chữ cái ASCII hoặc chữ số, phần còn lại cho phép thêm `.`, `_`, `-`.
2. Mật khẩu phải là chuỗi Unicode hợp lệ. API dùng `isWellFormed()` để từ chối surrogate đứng lẻ kể cả khi JSON biểu diễn dưới dạng escape. FE kiểm tra tương đương, dùng kiểm tra cặp surrogate nếu trình duyệt thiếu `isWellFormed()`. Mật khẩu phải có ít nhất một ký tự ngoài tập khoảng trắng của JavaScript `trim()` và ít nhất 8 điểm mã theo `[...password].length`. Emoji như `😀` tính một điểm mã. Chuỗi emoji ghép và dấu kết hợp được tính theo từng điểm mã cấu thành. Dùng kiểm tra tùy chỉnh cho ngưỡng này vì `minlength` HTML đếm đơn vị UTF-16.
3. Giới hạn tối đa 1.024 byte UTF-8, kể cả khoảng trắng đầu và cuối. FE dùng `TextEncoder`, BE dùng `Buffer.byteLength(password, 'utf8')`, sau khi xác thực Unicode. Dùng `trim()` chỉ để kiểm tra chuỗi toàn khoảng trắng. Băm đúng chuỗi nhập, giữ nguyên khoảng trắng và cách biểu diễn Unicode. API kiểm tra toàn bộ điều kiện trước khi gọi hàm băm hoặc ghi SQL.
4. Tái sử dụng `backend/password.js` với Argon2id, salt ngẫu nhiên 16 byte, 64 MiB, 3 lượt, song song mức 1. Không đưa mật khẩu hoặc hash vào phản hồi và log. Các hash đang lưu tiếp tục được bộ xác minh hiện hành đọc, kể cả với tài khoản có mật khẩu dưới 8 điểm mã.
5. Sau khi băm, `createMember` ghi một dòng qua câu lệnh tham số hóa ở chế độ autocommit. `UNIQUE` trên `username` là nơi phân xử hai lượt đua, theo cùng collation SQL Server dùng khi đăng nhập. Với tên mới và hai lượt hợp lệ trong hạn mức, đúng một INSERT commit và nhận 201. Lượt còn lại nhận 409 khi driver báo lỗi trùng khóa tên đăng nhập (2627 hoặc 2601). Lỗi SQL khác đi theo nhánh 500 hiện hành.

### Schema SQL Server

Tái sử dụng `backend/migrations/001-foundation.sql`. Ngưỡng là quy tắc tại API và giao diện, không cần migration hay cập nhật dữ liệu tài khoản.

| Cột `[__SCHEMA__].[users]` | Kiểu và ràng buộc |
| --- | --- |
| `id` | `int IDENTITY(1,1) PRIMARY KEY` |
| `username` | `nvarchar(255) NOT NULL UNIQUE` |
| `password_hash` | `varchar(255) NOT NULL`, chứa chuỗi Argon2id |
| `role` | `varchar(16) NOT NULL CHECK (role IN ('MEMBER', 'MANAGER'))` |

```sql
INSERT INTO [__SCHEMA__].[users] (username, password_hash, role)
VALUES (@username, @hash, 'MEMBER');
```

Tên schema lấy từ cấu hình đã xác thực. Bind `@username` kiểu `nvarchar(255)` và `@hash` kiểu `varchar(255)`.

## API và phân quyền

| Điểm vào | Hợp đồng |
| --- | --- |
| `POST /auth/register` | Công khai cùng origin. Nhận JSON `{"username":"demo.member176","password":"abc1234😀"}`. Trả `201 {"username":"demo.member176","role":"MEMBER"}` sau commit. Phiên được cấp ở bước đăng nhập thủ công. |
| `POST /auth/login` | Xác minh thông tin theo #111 và cấp cookie phiên. |
| `GET /auth/me`, `GET /equipment` | Kiểm tra phiên. Thành viên đã đăng nhập đọc được danh mục. |
| `POST /loan-requests/{id}/approve` | Kiểm tra vai trò quản lý từ dữ liệu máy chủ trước handler. Thành viên nhận `403 FORBIDDEN` trước khi đọc hoặc ghi yêu cầu. |

`POST /auth/register` dùng `Cache-Control: no-store` và trả lỗi dạng `{"code":"…"}`.

| HTTP | Mã | Điều kiện |
| --- | --- | --- |
| 400 | `INVALID_INPUT` | Thiếu hoặc sai trường, mật khẩu 7 điểm mã, Unicode lỗi, quá giới hạn, JSON/kiểu nội dung sai hoặc có trường dư. Từ chối toàn bộ payload nếu gửi `role: MANAGER`. |
| 403 | `ORIGIN_FORBIDDEN` | Origin thiếu hoặc sai. |
| 409 | `USERNAME_TAKEN` | Tên trùng theo khóa duy nhất của SQL Server. |
| 429 | `REGISTER_RATE_LIMITED` | Vượt hạn mức theo IP, có `Retry-After`. |
| 500 | `INTERNAL_ERROR` | Lỗi xử lý hoặc lưu ngoài dự kiến. |

API nghiệp vụ tra cookie phiên và lấy vai trò từ `users`. Khách hoặc phiên hết hạn nhận `401 AUTH_REQUIRED`. API ghi của quản lý kiểm tra quyền, origin và CSRF trước thao tác nghiệp vụ. Khi tạo yêu cầu mượn, API lấy người mượn từ phiên và ghi `PENDING`. Phạm vi đọc của thành viên được xác định theo người sở hữu.

## Phụ thuộc vòng đời mượn thiết bị

#111 cung cấp phiên, vai trò, thiết bị mẫu, schema và định tuyến qua Caddy. #166 cung cấp màn đăng ký, API, lưu tài khoản và hợp đồng lỗi. Backend hiện dùng Node.js 26+ và driver `mssql`. #112–116 cung cấp lịch và vòng đời yêu cầu.

Các lệnh quản lý theo #114–116 chuyển `PENDING → APPROVED → HANDED_OVER → RETURNED` hoặc `PENDING → REJECTED`. Trong giao dịch T-SQL, khóa dòng thiết bị bằng `UPDLOCK, HOLDLOCK`, đọc lại yêu cầu rồi kiểm tra trạng thái nguồn. Khi duyệt, tìm yêu cầu khác của cùng thiết bị ở `APPROVED` hoặc `HANDED_OVER` có `existing.start_at < requested.end_at AND requested.start_at < existing.end_at`. Hai yêu cầu có thể cùng ở `PENDING`, nhưng khóa tuần tự hóa hai lần duyệt. Lượt gặp khoảng trùng trả lỗi xung đột và giữ trạng thái nguồn. Cập nhật có điều kiện theo trạng thái nguồn và ghi sự kiện trong một giao dịch. Chỉ mục duy nhất có lọc của #115 bảo đảm mỗi thiết bị chỉ có một yêu cầu `HANDED_OVER` tại một thời điểm. Chi tiết theo [#114](story-114-sa-design.md), [#115](story-115-sa-design.md) và [#116](story-116-sa-design.md).

## Bàn giao BA

Cập nhật SRS và prototype #166 tại biểu mẫu mở từ màn đăng nhập. Hiển thị đúng câu **Mật khẩu phải có ít nhất 8 ký tự** và báo tại trường mật khẩu khi nhập 7 điểm mã. Trình bày trạng thái đang gửi, xác nhận tạo tài khoản, đăng nhập thủ công và danh mục. Giữ các luồng lỗi tên trùng, hạn mức và lỗi mạng của #166. Nếu mất phản hồi, giao diện báo chưa xác định kết quả và cho phép thử đăng nhập hoặc gửi lại. Xóa mật khẩu khi đăng ký thành công hoặc rời biểu mẫu.

| Ca nghiệm thu | Kết quả quan sát |
| --- | --- |
| `abc1234` và `abc123😀` | Mỗi chuỗi có 7 điểm mã. Form báo lỗi. Gọi API trực tiếp với từng chuỗi và tên hợp lệ nhận 400 `INVALID_INPUT`, không có dòng mới. |
| `abc12345` và `abc1234😀` | Mỗi chuỗi có 8 điểm mã. Với tên mới hợp lệ, form cho gửi, API trả 201 và lưu `MEMBER`. |
| Thiếu, rỗng, 8 dấu cách, surrogate đứng lẻ, UTF-8 lỗi | API trả 400 và không ghi tài khoản. FE kiểm tra các giá trị nhập tương ứng. |
| 256 emoji `😀`, rồi thêm một ký tự ASCII | Với tên mới cho từng lượt, 1.024 byte được chấp nhận và 1.025 byte nhận 400. FE và API cho cùng kết quả. |
| Tài khoản sẵn có và hash | Đăng nhập bằng mật khẩu cũ. Với tài khoản mới, kiểm tra định dạng Argon2id trong SQL Server và xác minh bằng đăng nhập thủ công. |
| Quyền và cạnh tranh | Payload kèm vai trò quản lý nhận 400 và không tạo dòng. Thành viên mới nhận 403 ở API duyệt. Hai lượt đồng thời dùng cùng tên mới sau chuẩn hóa nhận một 201, một 409 và chỉ một dòng `MEMBER`. |
| Demo SQL Server | Dùng thiết bị và tài khoản tổng hợp. Mở đăng ký từ màn đăng nhập, thử `abc123😀`, thấy lỗi, sửa thành `abc1234😀`, nhận xác nhận, tự đăng nhập và mở danh mục. |

Lượt SA đối chiếu thiết kế với Redmine, bàn giao và mã nguồn. Các ca SQL Server và trình duyệt ở trên dùng để nghiệm thu bản triển khai #176.
