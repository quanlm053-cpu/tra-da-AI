# Thiết kế tự đăng ký tài khoản thành viên

Bàn giao BA task #168 cho Story #166, task SA #167. Căn cứ gồm tiêu chí Redmine #166–167, trạng thái và bàn giao #111–116 qua MCP Lending, cùng schema và mã nguồn hiện hành. Microsoft SQL Server và T-SQL là lựa chọn của người điều hành. Schema hiện hành trong workspace là căn cứ cho hợp đồng dữ liệu.

## HLD

Website và API dùng cùng origin HTTPS qua Caddy. Màn đăng nhập có liên kết **Đăng ký** mở biểu mẫu gồm tên đăng nhập và mật khẩu. Trình duyệt gửi JSON đến API công khai. Backend kiểm tra origin và dữ liệu, băm mật khẩu rồi ghi một tài khoản `MEMBER` vào SQL Server. Sau phản hồi thành công, giao diện xác nhận tài khoản đã tạo và cho khách quay về đăng nhập. Khách tự nhập thông tin đăng nhập và gửi qua luồng #111. Phiên do API đăng nhập cấp được dùng để đọc danh mục thiết bị.

Định danh đăng nhập là `username` của #111. Tài khoản khả dụng ngay khi câu lệnh ghi đã commit. Dùng cùng bảng tài khoản và cùng bộ xác minh mật khẩu. Luồng đăng ký chỉ tạo dòng tài khoản, còn việc tạo phiên thuộc `POST /auth/login`. Giữ vai trò và quyền hiện hành từ dữ liệu máy chủ.

## Schema và LLD ghi tài khoản

| Cột trong `[__SCHEMA__].[users]` | Hợp đồng từ migration nền tảng |
|---|---|
| `id` | `int IDENTITY(1,1) PRIMARY KEY`, SQL Server cấp. |
| `username` | `nvarchar(255) NOT NULL UNIQUE`, lưu dạng chuẩn của đăng nhập. |
| `password_hash` | `varchar(255) NOT NULL`, lưu chuỗi Argon2id tương thích bộ xác minh hiện hành. |
| `role` | `varchar(16) NOT NULL CHECK (role IN ('MEMBER', 'MANAGER'))`. Câu lệnh đăng ký cấp hằng `MEMBER`. |

Dùng tên schema đã được cấu hình và xác thực theo backend hiện hành. Dùng ràng buộc `UNIQUE` đã có, do đó thiết kế dùng migration #111 hiện hành trực tiếp. So sánh trùng dùng collation của cột `username`, cùng phép so sánh như truy vấn đăng nhập. Ký tự hoặc cách viết được collation coi là tương đương với tên đã có sẽ nhận lỗi trùng.

1. API chỉ chấp nhận đối tượng JSON có đúng hai khóa `username` và `password`. Tái dùng giới hạn body 8.192 byte của backend. Tên gốc tối đa 128 đơn vị UTF-16. Chuẩn hóa bằng `trim().toLowerCase()` như đăng nhập. Tên chuẩn dài 3–64 ký tự, bắt đầu bằng chữ cái ASCII hoặc chữ số, các ký tự tiếp theo có thể thêm dấu chấm, gạch dưới và gạch ngang. Kiểm tra toàn bộ chuỗi. Quy tắc định dạng mới áp dụng tại điểm vào đăng ký.
2. Mật khẩu là chuỗi, tối thiểu 12 điểm mã Unicode, tối đa 1.024 byte UTF-8, có ít nhất một ký tự khác khoảng trắng. Giữ nguyên giá trị đã nhập khi băm. Dùng `hashPassword` trong `backend/password.js`, Argon2id với salt ngẫu nhiên 16 byte cho mỗi lượt băm, bộ nhớ 64 MiB, 3 lượt và song song mức 1. Log chỉ ghi mã lỗi kỹ thuật đã lọc.
3. Thực hiện một câu lệnh T-SQL tham số hóa ở chế độ autocommit sau khi băm. Tham số `@username` kiểu `nvarchar(255)`, `@hash` kiểu `varchar(255)`.

   ```sql
   INSERT INTO [__SCHEMA__].[users] (username, password_hash, role)
   VALUES (@username, @hash, 'MEMBER');
   ```

4. Chỉ mục duy nhất của SQL Server phân xử hai lượt ghi cạnh tranh, kể cả từ hai kết nối riêng. Các lượt có cùng khóa chuẩn hóa hoặc bằng nhau theo collation cho đúng một commit khi tên ban đầu còn trống. Trong thao tác INSERT này, ánh xạ lỗi SQL Server 2627 hoặc 2601 do khóa duy nhất của `username` thành `409 USERNAME_TAKEN` bằng mã lỗi gốc của driver và phạm vi ràng buộc. Lỗi SQL khác trả `500 INTERNAL_ERROR`. Một câu lệnh INSERT đủ để bảo đảm tính nguyên tử. Trả 201 sau khi ghi thành công.
5. Nếu mất phản hồi sau khi gửi, giao diện báo chưa xác định kết quả. Khách có thể thử đăng nhập thủ công, hoặc gửi lại biểu mẫu. Lượt gửi lại sau một commit nhận 409. Giao diện chỉ hiển thị xác nhận tạo tài khoản khi đã nhận 201.

## API và quyền

Các đường dẫn dưới đây là đường dẫn thực tế của backend, được Caddy định tuyến cùng origin. Đăng ký áp dụng kiểm tra `Origin` chính xác như đăng nhập, yêu cầu `Content-Type: application/json` và hoạt động khi khách chưa có phiên. Đặt giới hạn riêng cho đăng ký trước bước Argon2id, đề xuất 10 lượt/IP/phút cho demo một tiến trình, dùng cơ chế nhận IP proxy tin cậy của #111. 429 trả `Retry-After` theo số giây. Dùng phản hồi xác thực có `Cache-Control: no-store` cho đăng ký.

| Điểm vào | Hợp đồng |
|---|---|
| `POST /auth/register` | Body ví dụ `{"username":"demo.member166","password":"Demo only 166!"}`. Thành công trả `201 {"username":"demo.member166","role":"MEMBER"}`. Phản hồi chỉ có tên chuẩn và vai trò. |
| `POST /auth/login` | Hợp đồng #111. Sau khi khách tự gửi thông tin, API xác minh hash, tạo phiên và cấp cookie. |
| `GET /auth/me`, `GET /equipment` | Tái sử dụng phiên #111 để tra cứu người dùng và danh mục. |
| `POST /loan-requests/{id}/approve` | Ví dụ API quản lý để kiểm chứng. Thành viên đã đăng ký và đăng nhập nhận `403 FORBIDDEN` trước khi handler đọc hoặc ghi yêu cầu. |

| HTTP | Body JSON | Điều kiện |
|---|---|---|
| 400 | `{"code":"INVALID_INPUT"}` | Thiếu trường, sai kiểu hoặc định dạng, JSON lỗi, sai loại nội dung, quá giới hạn body hoặc có khóa ngoài hợp đồng. Payload có `role`, kể cả `"role":"MANAGER"`, bị từ chối toàn bộ. |
| 403 | `{"code":"ORIGIN_FORBIDDEN"}` | Origin thiếu hoặc khác origin cấu hình. |
| 409 | `{"code":"USERNAME_TAKEN"}` | Tên đăng nhập đã có theo ràng buộc SQL. |
| 429 | `{"code":"REGISTER_RATE_LIMITED"}` | Vượt hạn mức đăng ký. |
| 500 | `{"code":"INTERNAL_ERROR"}` | Lỗi lưu hoặc lỗi xử lý ngoài dự kiến. |

Backend xác thực các API nghiệp vụ qua cookie phiên, tra phiên hợp lệ và lấy `role` từ `users`. Khách hoặc phiên hết hạn nhận `401 AUTH_REQUIRED`. API ghi yêu cầu quản lý kiểm tra vai trò trước handler, sau đó kiểm tra origin và CSRF theo cơ chế #111 trước thao tác nghiệp vụ. Tên đăng nhập từ form và vai trò trong trình duyệt không tham gia quyết định phân quyền.

## Phụ thuộc và chuyển trạng thái nghiệp vụ

- #111 cung cấp schema `users`, `sessions`, cơ chế kiểm tra phiên và vai trò, cấu hình Caddy và runtime Node.js có Argon2id. Các thiết bị tổng hợp trong danh mục #111 phục vụ demo.
- #112–113 cung cấp lịch và API yêu cầu mượn. Khi thành viên tạo yêu cầu qua API nghiệp vụ, máy chủ lấy `borrower_id` từ phiên và tạo ở `PENDING`. Thành viên đọc yêu cầu trong phạm vi sở hữu.
- #114–116 xử lý `PENDING → APPROVED → HANDED_OVER → RETURNED` và `PENDING → REJECTED`. Các lệnh quản lý lấy khóa dòng thiết bị `UPDLOCK, HOLDLOCK` rồi đọc lại yêu cầu dưới khóa. Khi duyệt, kiểm tra các khoảng `APPROVED` hoặc `HANDED_OVER` của yêu cầu khác trên cùng thiết bị với điều kiện `existing.start_at < requested.end_at AND requested.start_at < existing.end_at`. Nếu trùng thì trả xung đột và giữ trạng thái nguồn. Cập nhật trạng thái theo điều kiện trạng thái nguồn và ghi sự kiện trong cùng giao dịch. #115 dùng thêm chỉ mục duy nhất có lọc cho lượt đang `HANDED_OVER`. Chi tiết theo [duyệt và từ chối](story-114-sa-design.md), [giao thiết bị](story-115-sa-design.md) và [nhận lại thiết bị](story-116-sa-design.md).

## Bàn giao BA

SRS và prototype cần mô tả đường đi từ đăng nhập sang đăng ký, trạng thái đang gửi, phản hồi thành công và nút quay về đăng nhập. Hiển thị quy tắc dữ liệu trước khi gửi, báo lỗi dễ hiểu và cho sửa tên khi trùng. Sau thành công hoặc rời biểu mẫu, xóa mật khẩu khỏi giao diện. Cho phép quay về đăng nhập với tên đã tạo điền sẵn để khách tự nhập mật khẩu.

| Ca nghiệm thu | Kết quả quan sát |
|---|---|
| Đăng ký hợp lệ và đăng nhập thủ công | 201, UI xác nhận tạo tài khoản, phản hồi không cấp cookie phiên. Sau khi tự đăng nhập, xem được danh mục thiết bị. |
| Payload thêm vai trò quản lý | 400 và không có dòng tài khoản cho tên thử nghiệm mới. Lặp kiểm tra với trường ngoài hợp đồng khác. |
| Thành viên gọi thẳng lệnh quản lý | Dùng phiên của tài khoản vừa tạo và token CSRF hợp lệ, nhận 403. Trạng thái và nhật ký yêu cầu giữ nguyên. |
| Thiếu hoặc sai dữ liệu | 400 cho thiếu trường, tên sai định dạng, mật khẩu không đạt hoặc JSON lỗi. Kiểm tra không có dòng mới. |
| Đăng ký đồng thời | Hai lượt hợp lệ dùng cùng tên mới, gồm biến thể chữ hoa và khoảng trắng ở biên, cho một 201, một 409 và đúng một dòng `MEMBER` trong SQL Server. Hạn mức còn đủ cho cả hai lượt. |
| Lưu mật khẩu | Trên SQL Server thử nghiệm, trường lưu có định dạng Argon2id và khác mật khẩu nhập. Đăng nhập bằng mật khẩu gốc thành công. |
| Lỗi và phục hồi | Hiển thị thông báo trùng, chờ theo Retry-After khi quá hạn mức, và cách kiểm tra bằng đăng nhập nếu mất phản hồi. |

Demo và kiểm thử dùng tài khoản, mật khẩu và thiết bị tổng hợp. Lượt SA đối chiếu thiết kế với schema, điểm vào API và bản bàn giao hiện hành. Kiểm thử đăng ký đồng thời trên SQL Server và luồng trình duyệt thực hiện khi có bản triển khai.
