# SRS · Tự đăng ký tài khoản thành viên

Story #166 · BA #168 · Club Equipment Lending. Căn cứ là mô tả Redmine #166, #168 đọc qua MCP Lending và [thiết kế SA #167](story-166-sa-design.md).

## Luồng nghiệp vụ

1. Khách ở màn **Đăng nhập** chọn **Đăng ký**. Màn đăng ký ban đầu để trống, gồm **Tên đăng nhập** và **Mật khẩu**. Hiển thị quy tắc ngay cạnh trường. Có liên kết về đăng nhập.
2. Khi gửi, FE kiểm tra dữ liệu và đặt lỗi cạnh trường tương ứng. Nếu hợp lệ, hiển thị **Đang tạo tài khoản…** và khóa gửi lặp trong lúc chờ. BE kiểm tra lại toàn bộ dữ liệu, cấp vai trò `MEMBER` và lưu tài khoản.
3. Khi nhận 201, FE hiển thị **Đã tạo tài khoản** cùng tên đã chuẩn hóa. Nút **Về đăng nhập** điền sẵn tên này. Xóa mật khẩu khi thành công hoặc rời biểu mẫu.
4. Khách tự nhập mật khẩu và bấm **Đăng nhập** qua luồng #111. Phiên đăng nhập hợp lệ mở **Danh mục thiết bị**. Giao diện thành viên hiển thị chức năng theo quyền hiện hành, phía máy chủ áp dụng quyền cho từng API.

## Dữ liệu và hợp đồng FE/BE

| Hạng mục | Quy tắc |
| --- | --- |
| Tên đăng nhập | Chuỗi bắt buộc, tối đa 128 đơn vị UTF-16 trước khi áp dụng `trim().toLowerCase()`. Sau chuẩn hóa dài 3–64 ký tự, ký tự đầu là chữ cái ASCII hoặc số, phần còn lại có thể thêm dấu chấm, gạch dưới và gạch ngang. Kiểm tra toàn bộ giá trị. |
| Mật khẩu | Chuỗi bắt buộc, ít nhất 12 điểm mã Unicode, tối đa 1.024 byte UTF-8, có ít nhất một ký tự khác khoảng trắng. Giữ nguyên khi gửi và xác minh. FE dùng `autocomplete="new-password"` ở đăng ký và `current-password` ở đăng nhập. |
| Gửi đăng ký | `POST /auth/register`, cùng origin HTTPS, JSON tối đa 8.192 byte, đúng hai khóa `username` và `password`. Khách có thể gọi khi chưa có phiên. Dùng kiểm tra Origin và chính sách IP proxy tin cậy theo #111. |
| Thành công | `201 {"username":"demo.member166","role":"MEMBER"}` sau khi commit. Phản hồi có `Cache-Control: no-store` như các phản hồi đăng ký khác. Việc cấp cookie phiên thuộc `POST /auth/login`. |
| Lưu và phân quyền | Microsoft SQL Server. Dùng INSERT T-SQL có tham số, gán hằng `MEMBER`, lưu hash Argon2id tương thích bộ xác minh hiện hành. Ràng buộc UNIQUE của `users.username` và collation hiện hành quyết định trùng. Dùng phiên và vai trò đọc từ máy chủ khi kiểm tra API quản lý. |

## Ngoại lệ và phục hồi

| Điều kiện | Xử lý |
| --- | --- |
| Thiếu, sai kiểu, sai định dạng, JSON lỗi, sai loại nội dung, vượt kích thước hoặc có khóa dư | `400 INVALID_INPUT`. Với lỗi FE xác định được, đánh dấu trường và đưa focus đến trường lỗi đầu. Nếu chỉ nhận mã từ BE, báo “Thông tin đăng ký chưa hợp lệ. Hãy kiểm tra và thử lại.” Giữ dữ liệu để sửa trong phiên biểu mẫu. Yêu cầu bị từ chối toàn bộ, kể cả khi khóa dư là `role`. |
| Origin thiếu hoặc khác cấu hình | `403 ORIGIN_FORBIDDEN`. Báo “Không thể gửi đăng ký từ trang này. Hãy mở lại trang đăng nhập của CLB.” |
| Tên đã có hoặc mất lượt ghi cạnh tranh | `409 USERNAME_TAKEN`. Báo “Tên đăng nhập đã được sử dụng.” tại trường tên, giữ dữ liệu để sửa và gửi lại. |
| Vượt hạn mức | `429 REGISTER_RATE_LIMITED` kèm `Retry-After` theo giây. Báo thời gian còn lại, khóa nút gửi đến hết thời hạn. SA đề xuất 10 lượt/IP/phút cho demo một tiến trình. |
| Lỗi xử lý hoặc lưu | `500 INTERNAL_ERROR`. Báo “Chưa thể tạo tài khoản. Hãy thử lại.” Cho phép gửi lại, không hiển thị chi tiết SQL hoặc stack trace. |
| Mất mạng hoặc quá thời gian chờ sau khi gửi | Báo “Chưa xác định tài khoản đã được tạo. Bạn có thể thử đăng nhập hoặc gửi lại.” Giữ biểu mẫu khi thử lại. Nếu lượt trước đã commit, lượt gửi lại nhận 409. |
| Đăng nhập thất bại | Hiển thị lỗi đăng nhập theo #111 và cho nhập lại. |
| Danh mục đang tải, rỗng, lỗi hoặc phiên hết hạn | Báo “Đang tải danh mục…”, “Chưa có thiết bị trong danh mục.” hoặc báo lỗi kèm **Thử lại**. Khi API trả `401 AUTH_REQUIRED`, quay về đăng nhập. |
| Thành viên gọi API quản lý | `403 FORBIDDEN` trước handler nghiệp vụ. Trạng thái và nhật ký yêu cầu giữ nguyên. |

## Tiêu chí nghiệm thu

| Mã | Thực hiện | Kết quả |
| --- | --- | --- |
| AC01 | Từ đăng nhập mở đăng ký, gửi tên mới hợp lệ và mật khẩu đạt chuẩn bằng dữ liệu tổng hợp. | Có trạng thái đang gửi, một phản hồi 201, một tài khoản MEMBER và xác nhận tạo tài khoản. Phản hồi đăng ký không cấp cookie phiên. |
| AC02 | Chọn về đăng nhập sau AC01, tự nhập mật khẩu và gửi. | Tên chuẩn được điền sẵn, ô mật khẩu trống trước khi khách nhập. Đăng nhập tạo phiên, danh mục tải qua `GET /equipment`. |
| AC03 | Gọi trực tiếp đăng ký bằng tên mới và thêm `"role":"MANAGER"`. Lặp với một khóa dư khác. | Mỗi lượt nhận 400 và SQL Server không có dòng tương ứng. |
| AC04 | Dùng phiên thành viên vừa tạo, Origin và CSRF hợp lệ, gọi `POST /loan-requests/{id}/approve` với yêu cầu tổng hợp ở PENDING. | Nhận 403, yêu cầu giữ PENDING, không ghi sự kiện duyệt. |
| AC05 | Thử thiếu từng trường, sai kiểu, tên sai định dạng, mật khẩu ngắn/toàn khoảng trắng/quá số byte, JSON lỗi, sai loại nội dung và body quá giới hạn. Kiểm tra thêm biên 3/64 ký tự sau chuẩn hóa, 128 đơn vị UTF-16 trước chuẩn hóa và biên Unicode của mật khẩu. | UI nhận diện lỗi trường phù hợp. API trả 400 cho dữ liệu sai và không tạo dòng. Các giá trị hợp lệ tại biên được chấp nhận với tên mới. |
| AC06 | Gửi song song qua hai kết nối với cùng tên mới và đủ hạn mức. Lặp với hai biến thể viết hoa và khoảng trắng ở biên. | Mỗi cặp có đúng một 201 và một 409. Truy vấn SQL Server thấy đúng một dòng MEMBER cho khóa thử. UI lượt thua báo lỗi trùng cạnh trường tên. |
| AC07 | Kiểm tra dòng vừa tạo trong cơ sở dữ liệu thử nghiệm. | `password_hash` có định dạng Argon2id, khác mật khẩu gốc. Đăng nhập bằng mật khẩu gốc thành công và mật khẩu sai bị từ chối. |
| AC08 | Mô phỏng 429, 500, mất phản hồi sau commit và Origin sai. Dùng bàn phím để đi qua các màn. | UI hiển thị và phục hồi theo bảng ngoại lệ. Sau mất phản hồi có thể đăng nhập thủ công, gửi lại cùng tên nhận 409. Trình đọc màn hình nhận thông báo trạng thái và lỗi. |
| AC09 | Sau đăng nhập, lần lượt trả danh mục có dữ liệu, rỗng, lỗi tạm thời và phiên hết hạn. | Hiển thị các trạng thái tương ứng. Thử lại tải được danh mục khi dịch vụ phục hồi. Phiên hết hạn đưa về đăng nhập. |

## Bàn giao FE/BE

- Chốt khi tích hợp cách ánh xạ mã lỗi và đọc `Retry-After` theo giây. Hợp đồng 400 hiện chỉ có mã chung, lỗi chi tiết từng trường do FE xác định bằng cùng quy tắc với BE.
- Dùng giá trị `username` từ 201 làm tên điền sẵn. BE chuẩn hóa tên bằng cùng cách với đăng nhập, còn FE gửi giá trị gốc để BE áp dụng giới hạn trước chuẩn hóa.
- Xác nhận cấu hình hạn mức demo khi triển khai. Tester cần đủ hạn mức cho cả hai lượt ghi đồng thời và cần SQL Server thử nghiệm để kiểm tra số dòng, vai trò và hash.
- [Prototype](story-166-prototype.html) mở trực tiếp, mô phỏng bằng bộ nhớ của tab. Các lựa chọn mô phỏng chuyển trạng thái phục vụ BA, gồm ví dụ danh mục, thời gian chờ và lỗi. Kiểm thử hợp đồng HTTP, cookie, quyền, hash và ghi đồng thời thuộc bản triển khai.
