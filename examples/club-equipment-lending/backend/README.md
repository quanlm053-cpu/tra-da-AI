# Bàn giao backend Story #111–114

## Khởi tạo

Cần Node.js 26 trở lên và một cơ sở dữ liệu Microsoft SQL Server. Chạy lệnh trong thư mục backend. Mặc định, driver dùng TCP với chuỗi kết nối SQL Server của mssql. Windows dùng shared memory có thể đặt SQLSERVER_DRIVER=odbc và cung cấp chuỗi ODBC trong DATABASE_URL.

1. Chạy `npm install`.
2. Cấu hình `DATABASE_URL` và chạy `npm run migrate`.
3. Với demo/test, đặt `LENDING_ENV` thành `demo` hoặc `test`, cấp hai mật khẩu tổng hợp qua `DEMO_MEMBER_PASSWORD` và `DEMO_MANAGER_PASSWORD`, rồi chạy `npm run seed`. Seed giữ nguyên ID, vai trò và mật khẩu của các bản ghi đã tồn tại. Tài khoản mẫu là `demo.member` và `demo.manager`.
4. Đặt `APP_ORIGIN` thành origin HTTPS công khai, ví dụ `https://lending.example.test`, rồi chạy `npm start`. Đặt FE và API sau cùng một reverse proxy kết thúc TLS. API mặc định lắng nghe tại `127.0.0.1:3000`, có thể cấu hình bằng `HOST` và `PORT`.

## Tích hợp FE

### Đăng ký thành viên Story #166

Gửi `POST /auth/register` cùng origin HTTPS với `Content-Type: application/json` và đúng hai khóa `username`, `password`. Giới hạn JSON là 8.192 byte. Gửi tên gốc để máy chủ kiểm tra tối đa 128 đơn vị UTF-16 rồi chuẩn hóa bằng `trim().toLowerCase()`. Tên chuẩn dài 3–64 ký tự, bắt đầu bằng chữ ASCII hoặc số, các ký tự tiếp theo có thể thêm `.`, `_` và `-`. Mật khẩu giữ nguyên, cần ít nhất 8 điểm mã Unicode, tối đa 1.024 byte UTF-8 và có ít nhất một ký tự khác khoảng trắng. FE kiểm tra Unicode hợp lệ trước khi đếm bằng `[...password].length` và đo byte bằng `TextEncoder`. Hiển thị “Mật khẩu phải có ít nhất 8 ký tự” khi thiếu điểm mã. Ví dụ `abc123😀` nhận 400 `INVALID_INPUT` và `abc1234😀` nhận 201 với tên mới hợp lệ.

`201` trả `{ "username": "demo.member166", "role": "MEMBER" }` và `Cache-Control: no-store`. Hiển thị xác nhận, xóa mật khẩu và dùng tên trả về để điền sẵn khi khách quay lại đăng nhập. Khách tự gửi `POST /auth/login` để nhận cookie phiên rồi mở `GET /equipment`.

| Phản hồi | Xử lý trên FE |
| --- | --- |
| `400 INVALID_INPUT` | Báo dữ liệu đăng ký sai. Xác định lỗi từng trường theo các quy tắc trên. |
| `403 ORIGIN_FORBIDDEN` | Hướng khách mở trang đăng nhập qua origin của CLB. |
| `409 USERNAME_TAKEN` | Báo trùng cạnh trường tên và cho sửa. |
| `429 REGISTER_RATE_LIMITED` | Đọc `Retry-After` theo giây. Đăng ký có hạn mức riêng 10 lượt/IP/phút trên mỗi tiến trình. |
| `500 INTERNAL_ERROR` | Báo lỗi tạm thời và cho gửi lại. |
| Mất phản hồi | Báo kết quả chưa xác định. Cho thử đăng nhập thủ công hoặc gửi lại. Nếu lượt trước đã ghi thành công, lượt gửi lại nhận `409`. |

SQL Server dùng ràng buộc `UNIQUE` của `users.username` từ migration 001 để phân xử các lượt đăng ký đồng thời. Chạy `npm run test:sqlserver` với database thử nghiệm để kiểm tra một lượt `201`, một lượt `409`, hash Argon2id và quyền của thành viên mới. Dùng dữ liệu tổng hợp, ví dụ `demo.member166` và `Demo only 166!`.

### Phiên và danh mục

| API | Yêu cầu và phản hồi |
| --- | --- |
| `POST /auth/login` | Gửi JSON `{ username, password }` từ origin ứng dụng. Nhận `200` với `{ id, username, role, csrf_token }` và cookie phiên. |
| `GET /auth/me` | Nhận `200` với cùng cấu trúc. Gọi khi mở hoặc tải lại màn nghiệp vụ. |
| `GET /equipment` | Nhận `200` với mảng JSON chứa `{ id, asset_code, name }`. Dùng `asset_code` để phân biệt hai máy chiếu và dùng `id` để liên kết lịch Story #112. |
| `GET /equipment/{id}/availability?from=…&to=…` | Thành viên và quản lý dùng cookie phiên để nhận `200` với `{ equipment_id, timezone, as_of, available }`. |
| `POST /auth/logout` | Gửi header `X-CSRF-Token` lấy từ login hoặc me. Nhận `204` với body rỗng. |

Trình duyệt gửi cookie qua yêu cầu cùng origin. Cookie `__Host-lending_session` có `Secure`, `HttpOnly`, `SameSite=Lax` và thời hạn cố định 8 giờ. Giữ `csrf_token` trong bộ nhớ FE và gửi qua `X-CSRF-Token` cho các lệnh ghi có phiên.

Lỗi có cấu trúc `{ code }`. Với `401 AUTH_REQUIRED`, FE xóa dữ liệu phiên và điều hướng về đăng nhập, kể cả khi mở thẳng màn nghiệp vụ. Với `403 FORBIDDEN`, giữ phiên và báo thiếu quyền. Với `403 CSRF_INVALID`, tải lại `/auth/me` để lấy token hiện hành. Điều hướng quản lý dựa trên vai trò `MANAGER`. Danh mục có thể trả mảng rỗng.

Đăng nhập trả `400 INVALID_INPUT` nếu dữ liệu thiếu hoặc sai định dạng, `401 INVALID_CREDENTIALS` cho cả tên và mật khẩu sai, `403 ORIGIN_FORBIDDEN` nếu sai origin, và `429 LOGIN_RATE_LIMITED` kèm `Retry-After` tính bằng giây. Giới hạn trong mỗi tiến trình là 10 lần gửi mỗi phút theo IP khách.

Caddy ghi đè `X-Lending-Client-IP` bằng IP của kết nối tới Caddy. API chỉ dùng header chứa một IP hợp lệ từ kết nối TCP có nguồn `127.0.0.1`. Các trường hợp khác dùng IP của kết nối tới API. Khi triển khai theo `Caddyfile`, giữ API trên loopback và cho khách truy cập qua Caddy. Cấu hình này tin cậy tiến trình cục bộ có thể kết nối từ `127.0.0.1`.

Các route nghiệp vụ đăng ký qua `routes` của `createApp` đều yêu cầu phiên. Route quản lý đặt `role: 'MANAGER'` để kiểm tra quyền trước khi chạy handler. Kiểm tra CSRF tự áp dụng cho lệnh ghi. Hai mã `DEMO-01` và `DEMO-02` có ID vật lý riêng.

### Lịch trống Story #112

Chạy `npm run migrate` để áp dụng `002-loan-requests.sql` trước khi gọi API. Dùng ID vật lý từ `GET /equipment`. Chuyển thời gian nhập theo giờ CLB Asia/Bangkok (UTC+07:00), độc lập với múi giờ trình duyệt. Gửi đúng một giá trị cho mỗi tham số `from` và `to`, ở dạng ISO 8601 có giây và offset, với tối đa ba chữ số phần giây. Dùng `URLSearchParams` để mã hóa dấu cộng trong offset.

```js
const query = new URLSearchParams({
  from: '2026-11-16T09:00:00+07:00',
  to: '2026-11-16T13:00:00+07:00',
});
const response = await fetch(`/equipment/${equipmentId}/availability?${query}`);
```

Mỗi phần tử `available` có `start_at` và `end_at` theo UTC, sắp xếp theo giờ bắt đầu. Định dạng cả hai mốc theo `timezone` trong phản hồi. `as_of` là giờ UTC ghi sau khi đọc lịch. Mảng rỗng nghĩa là cả cửa sổ bận. API dùng `Cache-Control: no-store` và payload chỉ chứa thiết bị, múi giờ và các mốc thời gian.

Xử lý `400 INVALID_INPUT` bằng cách giữ và cho sửa đầu vào. Với `401 AUTH_REQUIRED`, quay lại luồng đăng nhập. Với `403 FORBIDDEN`, báo thiếu quyền. Với `404 NOT_FOUND`, cho tải lại danh mục. Với `500 INTERNAL_ERROR` hoặc lỗi mạng, cho thử lại cùng đầu vào. Khi đầu vào thay đổi, xóa kết quả cũ và bỏ qua phản hồi của lượt đã bị thay thế.

### Gửi và theo dõi yêu cầu mượn Story #113

Chạy `npm run migrate` để bổ sung chỉ mục đọc theo người mượn trên bảng `loan_requests` của #112. Ba tuyến dưới đây dùng cookie phiên có vai trò `MEMBER` và trả `Cache-Control: no-store`.

| API | Yêu cầu và phản hồi |
| --- | --- |
| `POST /loan-requests` | Gửi JSON chỉ gồm `equipment_id` kiểu số nguyên, `start_at`, `end_at` và header `X-CSRF-Token`. Nhận `201`, đối tượng đã lưu ở trạng thái `PENDING` và `Location: /loan-requests/{id}`. Các lượt gửi trùng giờ tạo các ID riêng. |
| `GET /loan-requests` | Nhận `200` với mảng yêu cầu của phiên, sắp theo thời điểm tạo giảm dần rồi ID giảm dần. |
| `GET /loan-requests/{id}` | Nhận `200` với chi tiết hiện hành của yêu cầu thuộc phiên. |

Mỗi đối tượng có `id`, `equipment_id`, `start_at`, `end_at`, `created_at` và `status`. Nối tên và mã tài sản từ `GET /equipment`. Gửi mốc ISO 8601 có giây, offset và tối đa ba chữ số phần giây. API trả UTC, FE hiển thị theo Asia/Bangkok. Khi chuyển từ lịch #112 sang biểu mẫu, đề xuất dùng `equipment_id`, `start_at`, `end_at` làm tên tham số điền sẵn trên URL giao diện. Tạo URL bằng `URLSearchParams` và để thành viên kiểm tra lại trước khi gửi. Dùng đường dẫn giao diện riêng để hiển thị chi tiết sau khi tạo.

`404 NOT_FOUND` khi POST nghĩa là thiết bị không tồn tại. Khi GET chi tiết, cùng phản hồi này áp dụng cho ID chưa tồn tại và yêu cầu của thành viên khác. Giữ dữ liệu nhập khi nhận `400 INVALID_INPUT`. Nếu POST mất phản hồi hoặc trả `500 INTERNAL_ERROR`, hướng dẫn thành viên kiểm tra danh sách trước khi gửi lại.

### Duyệt và từ chối Story #114

Chạy `npm run migrate` để áp dụng `004-loan-events.sql`. Với cookie phiên `MANAGER`, `GET /loan-requests` trả toàn bộ yêu cầu `PENDING`, sắp theo `created_at` rồi `id` tăng dần. Hàng đợi rỗng trả `[]`. `GET /loan-requests/{id}` trả chi tiết ở mọi trạng thái. Hai API đọc này thêm `borrower_id`, `borrower_username`, `equipment_name` và `equipment_asset_code` vào các trường của #113.

Gọi `POST /loan-requests/{id}/approve` hoặc `POST /loan-requests/{id}/reject` với cookie phiên quản lý, header `X-CSRF-Token` và body rỗng. `200` trả bản ghi đã commit gồm các trường của #113 và `borrower_id`. Chi tiết GET cung cấp các trường bổ sung từ JOIN. Ngày giờ API là UTC ISO 8601, FE hiển thị theo Asia/Bangkok.

- Với `409 SCHEDULE_CONFLICT`, làm mới hàng đợi. Yêu cầu vẫn `PENDING` và quản lý có thể từ chối.
- Với `409 INVALID_TRANSITION`, tải lại chi tiết và hàng đợi. Chỉ bật thao tác khi chi tiết mới là `PENDING`.
- Với `500 INTERNAL_ERROR`, timeout hoặc mất mạng khi ghi, tải lại chi tiết rồi đồng bộ hàng đợi trước khi cho phép gửi lệnh mới.
- `400 INVALID_INPUT` áp dụng cho ID sai cú pháp hoặc ngoài miền `int` dương. `404 NOT_FOUND` áp dụng cho ID hợp lệ nhưng không tồn tại.

Các lệnh đổi trạng thái khóa dòng thiết bị trước rồi khóa yêu cầu. Cập nhật và ghi sự kiện vào `loan_events` trong cùng giao dịch. Các lệnh giao và nhận lại ở #115–116 cần dùng cùng thứ tự khóa.

## Kiểm thử

- `npm test` chạy kiểm thử HTTP với kho dữ liệu thử nghiệm trong bộ nhớ.
- `npm run test:sqlserver` kiểm tra migration và seed lặp, phiên, lịch, API yêu cầu mượn và các lệnh quyết định đồng thời, bao gồm hoàn tác khi ghi sự kiện lỗi. Đặt `TEST_DATABASE_URL` trỏ tới DB kiểm thử dùng dữ liệu tổng hợp. Tài khoản DB cần quyền tạo schema thử nghiệm. Bộ kiểm thử tạo và dọn schema riêng.

### SQL Server kiểm thử trên máy Windows

Dùng database riêng `ClubEquipmentLending_Test` và tài khoản Windows có quyền tạo schema test. Với kết nối shared memory qua ODBC Driver 17, đặt `SQLSERVER_DRIVER=odbc` và cấu hình `TEST_DATABASE_URL` bằng chuỗi ODBC phù hợp với máy. Kết quả xác minh SQL Server trước đây của Story #111 nằm trong [bàn giao #111](../story-111-sqlserver-verification.md).

## Bàn giao FE · Xác nhận giao thiết bị (#115)

- Quản lý gọi `GET /loan-requests?status=APPROVED` để lấy danh sách đã duyệt với cùng các trường của hàng đợi #114. Mở và tải lại chi tiết bằng `GET /loan-requests/{id}`. Thành viên dùng API danh sách và chi tiết hiện có để đọc trạng thái của yêu cầu mình sở hữu.
- Quản lý gọi `POST /loan-requests/{id}/handover` với cookie phiên, header `X-CSRF-Token` và body rỗng. Phản hồi `200` có cùng các trường với lệnh duyệt #114 và `status: "HANDED_OVER"`. Hiển thị **Đã giao** và làm mới danh sách đã duyệt. Người giao và thời điểm UTC lưu trong nhật ký nội bộ.
- Với `409 EQUIPMENT_IN_USE`, giữ **Đã duyệt** và hiển thị **Thiết bị vẫn đang được giữ. Hãy xác nhận nhận lại trước khi giao lượt này.** Với `409 INVALID_TRANSITION`, tải lại chi tiết để lấy trạng thái hiện tại. Nếu mất phản hồi hoặc gặp `500 INTERNAL_ERROR`, tải lại chi tiết trước khi cho phép gửi lại.
- Các lỗi còn lại gồm `400 INVALID_REQUEST` cho ID giao sai định dạng, `404 NOT_FOUND`, `401 AUTH_REQUIRED` và `403 FORBIDDEN` hoặc `CSRF_INVALID`.

## Bàn giao FE · Xác nhận nhận lại thiết bị (#116)

- Quản lý lấy danh sách bằng `GET /loan-requests?status=HANDED_OVER` và xác nhận bằng `POST /loan-requests/{id}/return` với cookie phiên, header `X-CSRF-Token` và body rỗng. Dùng đường dẫn cùng origin.
- Phản hồi `200` sau commit có DTO lệnh giao với `status: "RETURNED"` và thêm `returned_by` (ID), `returned_by_username` (tên đăng nhập), `returned_at` (ISO 8601 UTC). Hiển thị **Đã trả**, tên người nhận và giờ theo `Asia/Bangkok`, rồi tải lại danh sách đã giao. Chi tiết quản lý `GET /loan-requests/{id}` đọc cùng dữ liệu nhận từ nhật ký. Với bản ghi cũ đã trả mà thiếu sự kiện, các trường nhận vắng mặt.
- Thành viên tải lại danh sách hoặc chi tiết hiện có để thấy `RETURNED` và giờ đặt gốc. Tra cứu lịch mới bỏ khoảng đặt đã trả. Tiếp tục dùng lệnh giao #115 để kiểm tra thiết bị đang rảnh và giao lượt kế tiếp.
- Với `409 INVALID_TRANSITION`, `500 INTERNAL_ERROR` hoặc mất phản hồi, tải lại chi tiết trước khi cho gửi lại. Nếu đã trả, hiển thị kết quả đã lưu. Nếu còn đã giao, cho xác nhận lại. Nếu tải chi tiết lỗi, cho thử tải lại chi tiết. Lỗi khác gồm `400 INVALID_INPUT`, `404 NOT_FOUND`, `401 AUTH_REQUIRED` và `403 FORBIDDEN` hoặc `CSRF_INVALID`.
- Backend dùng schema từ migration 002, 004 và 005 để ghi sự kiện và giải phóng thiết bị trong cùng giao dịch.
