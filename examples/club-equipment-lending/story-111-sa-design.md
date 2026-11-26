# Thiết kế nền tảng Club Equipment Lending

Bàn giao BA cho Story #111, task SA #117. Đối chiếu với yêu cầu PM, HLD trước và tiêu chí Stories #112–116 trong MCP Lending.

## HLD

Ứng dụng web cùng origin phục vụ giao diện và API. API gồm xác thực và phiên, phân quyền, danh mục thiết bị và các mô-đun lịch, yêu cầu, giao nhận. SQL Server là nguồn dữ liệu chung cho API. Story #111 cung cấp đăng nhập, đăng xuất, nhận diện phiên, danh sách thiết bị mẫu và lớp kiểm tra quyền dùng chung. Stories #112–116 phụ thuộc vào lớp này và khóa định danh thiết bị vật lý để triển khai lịch và luồng mượn. Các cơ chế nghiệp vụ bên dưới là hợp đồng thiết kế cho các Story phụ thuộc.

Chọn tài khoản cục bộ, mật khẩu băm Argon2id và phiên lưu phía máy chủ. Mỗi tài khoản có một vai trò. Quản lý xử lý yêu cầu toàn CLB. Giữ quy ước hiển thị `Asia/Bangkok` từ HLD trước, dùng HTTPS và khóa chống CSRF cho các lệnh có thay đổi dữ liệu. Phụ thuộc triển khai gồm thư viện Argon2id, cơ chế tạo token ngẫu nhiên bảo mật, SQL Server hỗ trợ giao dịch và khóa dòng, cấu hình HTTPS, múi giờ CLB và bí mật seed của môi trường demo. Công nghệ giao diện và framework máy chủ để giai đoạn triển khai chọn.

## Schema

| Bảng | Cột và ràng buộc |
|---|---|
| `users` | `id` PK, `username` UNIQUE NOT NULL, `password_hash` NOT NULL, `role` NOT NULL CHECK thuộc `MEMBER`, `MANAGER`. Tên đăng nhập mẫu dùng chữ thường. |
| `sessions` | `token_hash` PK, `user_id` FK NOT NULL, `expires_at` datetime2(3) UTC NOT NULL. Chỉ lưu bản băm của token ngẫu nhiên. |
| `equipment` | `id` PK, `asset_code` UNIQUE NOT NULL, `name` NOT NULL. Một dòng cho một thiết bị vật lý, kể cả hai thiết bị cùng tên. |
| `loan_requests` | Dùng từ #113. `id` PK, `equipment_id` và `borrower_id` FK NOT NULL, `start_at`, `end_at`, `created_at` datetime2(3) UTC NOT NULL, `status` NOT NULL giới hạn theo vòng đời. CHECK `start_at < end_at`. Thiết bị, người mượn và giờ đặt cố định sau khi tạo trong các Story hiện tại. |
| `loan_events` | Dùng từ #114. `id` PK, `request_id` và `actor_id` FK NOT NULL, `from_status`, `to_status`, `occurred_at` datetime2(3) UTC NOT NULL. Ghi sự kiện cùng giao dịch đổi trạng thái. |

Đề xuất chỉ mục yêu cầu theo `(equipment_id, status, start_at)` cho lịch và `(borrower_id, created_at)` cho lịch sử. Từ #115 thêm chỉ mục unique từng phần trên `equipment_id` với điều kiện `status = 'HANDED_OVER'` để bảo vệ ràng buộc một lượt đang giữ thiết bị.

Seed demo/test theo khóa ổn định `username` và `asset_code`, có thể chạy lại mà vẫn chỉ có một bản ghi cho mỗi khóa. Tạo `demo.member` và `demo.manager` với mật khẩu tổng hợp cấp qua cấu hình môi trường demo/test, băm khi tạo. Tạo hai máy chiếu mẫu cùng tên, mã `DEMO-01` và `DEMO-02`, với hai ID riêng. Lịch trống ban đầu gắn với từng ID. Khi mô-đun lịch có sẵn, dùng fixture yêu cầu tổng hợp trên một ID để kiểm tra ID kia vẫn trống. Seed được bật riêng cho môi trường demo/test.

## LLD xác thực và kiểm tra quyền

1. Đăng nhập kiểm tra thông tin tài khoản, trả cùng mã lỗi cho tên hoặc mật khẩu sai, giới hạn tần suất thử và tạo phiên mới với token ngẫu nhiên. Đặt token trong cookie `HttpOnly`, `Secure`, `SameSite=Lax`. Đăng xuất thu hồi phiên và xóa cookie. Áp dụng kiểm tra origin cho đăng nhập và token CSRF gắn phiên cho các lệnh ghi sau đăng nhập.
2. Middleware mặc định yêu cầu phiên còn hạn trên mọi API nghiệp vụ, lấy danh tính và vai trò hiện tại từ máy chủ. Vai trò, người mượn và trạng thái do API xác định. Bảo vệ cả đường dẫn trực tiếp đến màn nghiệp vụ. Giao diện chuyển người chưa có phiên đến đăng nhập và chỉ hiển thị thao tác phù hợp vai trò.
3. API kiểm tra vai trò trước khi truy vấn đối tượng cho lệnh quản lý. Với thành viên, danh sách và chi tiết yêu cầu đều truy vấn theo `borrower_id = session.user_id`. Lỗi thiếu phiên trả `401`, sai vai trò trả `403`, đối tượng thiếu hoặc nằm ngoài phạm vi sở hữu trả `404`. Kiểm tra trạng thái nghiệp vụ diễn ra sau kiểm tra quyền.

## Hợp đồng API

| Story | API | Hợp đồng thành công |
|---|---|---|
| #111 | `POST /auth/login` | Nhận `username`, `password`. Trả `200`, đặt cookie phiên và trả `id`, `username`, `role`, token CSRF. |
| #111 | `GET /auth/me`, `POST /auth/logout` | Trả thông tin phiên cùng token CSRF với `200`. Đăng xuất trả `204`. |
| #111 | `GET /equipment` | Hai vai trò nhận `200` với danh sách `id`, `asset_code`, `name`. |
| #112 | `GET /equipment/{id}/availability?from=…&to=…` | Trả `equipment_id`, `timezone`, `as_of` và các khoảng trống có `start_at`, `end_at`. Hai vai trò tra cứu được. Kết quả chỉ chứa dữ liệu lịch. |
| #113 | `POST /loan-requests` | Thành viên gửi `equipment_id`, `start_at`, `end_at`. Trả `201` với yêu cầu `PENDING`. |
| #113–114 | `GET /loan-requests`, `GET /loan-requests/{id}` | Thành viên xem yêu cầu của mình. Quản lý xem hàng đợi và chi tiết toàn CLB. |
| #114–116 | `POST /loan-requests/{id}/{action}` | Quản lý gọi `approve`, `reject`, `handover`, `return`. Trả `200` với yêu cầu đã cập nhật. |

Phản hồi lỗi dùng `code` ổn định để giao diện chọn thông báo. Dữ liệu đầu vào sai trả `400`. Các lỗi nghiệp vụ `409` gồm `SCHEDULE_CONFLICT`, `INVALID_TRANSITION`, `EQUIPMENT_IN_USE`.

## LLD lịch, trạng thái và cạnh tranh

- Lưu thời điểm theo UTC, nhận ISO 8601 kèm offset, hiển thị theo múi giờ CLB có nhãn rõ. Mọi cửa sổ đặt hoặc tra cứu là khoảng nửa mở `[start, end)` với `start < end`. Hai khoảng trùng khi `existing.start_at < requested.end_at AND requested.start_at < existing.end_at`. Các khoảng 09:00–10:00 và 10:00–11:00 sát biên.
- Lấy các khoảng của đúng thiết bị đang `APPROVED` hoặc `HANDED_OVER` giao với cửa sổ tra cứu. Cắt theo biên cửa sổ, hợp nhất rồi lấy phần bù. `PENDING`, `REJECTED`, `RETURNED` không chiếm lịch. Lịch phản ánh giờ đặt và trạng thái tại thời điểm tra cứu. Việc giao thiết bị kiểm tra tình trạng giữ thực tế, kể cả khi lượt trước đã quá giờ.
- Tạo yêu cầu ở `PENDING` kể cả khi trùng giờ. Các lệnh hợp lệ gồm `PENDING → APPROVED`, `PENDING → REJECTED`, `APPROVED → HANDED_OVER`, `HANDED_OVER → RETURNED`. Hai trạng thái `REJECTED` và `RETURNED` kết thúc luồng.
- Sau kiểm tra quyền quản lý, bắt đầu giao dịch SQL Server `READ COMMITTED`. Đọc ID thiết bị của yêu cầu, khóa dòng thiết bị bằng `SELECT … WITH (UPDLOCK, HOLDLOCK)`, sau đó đọc và khóa dòng yêu cầu. Mọi lệnh đổi trạng thái dùng thứ tự này. Kiểm tra trạng thái nguồn dưới khóa, trả `409 INVALID_TRANSITION` nếu sai.
- Khi duyệt, chạy truy vấn giao nhau bằng câu lệnh riêng sau khi đã lấy khóa thiết bị. Chỉ xét các yêu cầu khác của cùng thiết bị ở `APPROVED` hoặc `HANDED_OVER`. Nếu trùng, rollback và trả `409 SCHEDULE_CONFLICT`, yêu cầu vẫn `PENDING`. Khi hai lượt duyệt trùng nhau chạy đồng thời, lượt thứ hai chờ khóa rồi thấy kết quả đã commit của lượt thứ nhất. Nếu lượt thứ nhất rollback, lượt thứ hai được xét theo dữ liệu hiện hành.
- Khi giao, kiểm tra dưới khóa thiết bị rằng không có lượt khác đang `HANDED_OVER`. Nếu đang có người giữ, trả `409 EQUIPMENT_IN_USE` và giữ yêu cầu ở `APPROVED`. Khi nhận lại thành công, `RETURNED` giải phóng phần lịch còn lại và cho phép giao lượt đã duyệt tiếp theo.
- Cập nhật trạng thái và ghi sự kiện với người thao tác từ phiên, thời gian máy chủ, trong cùng giao dịch. Chỉ trả thành công sau commit. Nếu ghi sự kiện lỗi, rollback cả thay đổi. Lệnh lặp lại sau khi giao dịch trước đã thành công trả `409 INVALID_TRANSITION`. Giao diện tải lại trạng thái hiện tại trước khi cho thao tác tiếp.

## Bàn giao SRS và prototype

| Tiêu chí #111 | Kịch bản BA cần thể hiện |
|---|---|
| Tài khoản mẫu cho hai vai trò | Đăng nhập lần lượt bằng hai tài khoản demo, hiển thị đúng vai trò và thao tác. Đăng xuất rồi gọi lại API nghiệp vụ bằng cookie cũ phải nhận `401`. |
| Hai thiết bị vật lý có lịch riêng | Danh sách hiển thị hai thiết bị cùng tên với hai mã khác nhau. Khi có #112, prototype thể hiện chuyển thiết bị đổi lịch. Fixture khoảng bận của thiết bị thứ nhất không làm đổi lịch thiết bị thứ hai. |
| Chặn khách chưa đăng nhập | Mở trực tiếp màn nghiệp vụ và gọi trực tiếp `GET /equipment` khi thiếu phiên. Màn hình chuyển đến đăng nhập, API trả `401`. |
| Chặn thành viên gọi lệnh quản lý | Kiểm chứng lớp quyền quản lý ở #111 với phiên thành viên hợp lệ. Khi endpoint quản lý được triển khai ở #114–116, gửi trực tiếp lệnh với phiên và CSRF hợp lệ, kỳ vọng `403` và không đổi trạng thái. |

Khi BA đặc tả #112–116, dùng thêm các ca duyệt đồng thời hai yêu cầu giao nhau, hai yêu cầu sát biên, hai thiết bị cùng giờ, truy cập yêu cầu người khác, trả sớm và giao lượt tiếp theo khi lượt trước chưa trả. Prototype quản lý hiển thị lý do xung đột và trạng thái sau khi tải lại.

## Quyết định cập nhật

Người điều hành chọn Microsoft SQL Server cho toàn bộ dự án. Dùng T-SQL, truy vấn có tham số và thời gian UTC từ SYSUTCDATETIME(). Giữ nguyên hợp đồng HTTP của SRS.
