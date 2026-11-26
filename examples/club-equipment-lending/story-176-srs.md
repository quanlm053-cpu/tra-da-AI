# SRS · Hạ độ dài tối thiểu của mật khẩu đăng ký xuống 8 ký tự

Story #176 · BA #178 · Club Equipment Lending. Căn cứ là Redmine #176, #178 và #166 đọc qua MCP Lending, [thiết kế SA #177](story-176-sa-design.md) và [SRS #166](story-166-srs.md). Quy tắc mới áp dụng khi đăng ký. Luồng đăng nhập tiếp tục xác minh mật khẩu và hash hiện có.

## Luồng nghiệp vụ

1. Khách ở màn **Đăng nhập** chọn **Đăng ký**. Màn đăng ký ban đầu để trống, gồm **Tên đăng nhập** và **Mật khẩu**. Hiển thị quy tắc ngay cạnh trường. Có liên kết về đăng nhập.
2. Khi gửi, FE kiểm tra dữ liệu và đặt lỗi cạnh trường tương ứng. Nếu hợp lệ, hiển thị **Đang tạo tài khoản…** và khóa gửi lặp trong lúc chờ. BE kiểm tra lại toàn bộ dữ liệu, cấp vai trò `MEMBER` và lưu tài khoản.
3. Khi nhận 201, FE hiển thị **Đã tạo tài khoản** cùng tên đã chuẩn hóa. Nút **Về đăng nhập** điền sẵn tên này. Xóa mật khẩu khi thành công hoặc rời biểu mẫu.
4. Khách tự nhập mật khẩu và bấm **Đăng nhập** qua luồng #111. Phiên đăng nhập hợp lệ mở **Danh mục thiết bị**. Giao diện thành viên hiển thị chức năng theo quyền hiện hành, phía máy chủ áp dụng quyền cho từng API.

## Dữ liệu và hợp đồng FE/BE

| Hạng mục | Quy tắc |
| --- | --- |
| Tên đăng nhập | Chuỗi bắt buộc, tối đa 128 đơn vị UTF-16 trước khi áp dụng `trim().toLowerCase()`. Sau chuẩn hóa dài 3–64 ký tự, ký tự đầu là chữ cái ASCII hoặc số, phần còn lại có thể thêm dấu chấm, gạch dưới và gạch ngang. Kiểm tra toàn bộ giá trị. |
| Mật khẩu | Chuỗi bắt buộc, Unicode hợp lệ, ít nhất 8 điểm mã Unicode, tối đa 1.024 byte UTF-8, có ít nhất một ký tự khác khoảng trắng theo `trim()`. Hiển thị **Mật khẩu phải có ít nhất 8 ký tự** cạnh trường và dùng đúng câu này làm lỗi khi nhập 7 điểm mã hợp lệ có ký tự khác khoảng trắng. Giữ nguyên toàn bộ chuỗi khi gửi, băm và xác minh, kể cả khoảng trắng biên và dấu kết hợp. FE dùng `autocomplete="new-password"` ở đăng ký và `current-password` ở đăng nhập. |
| Gửi đăng ký | `POST /auth/register`, cùng origin HTTPS, JSON tối đa 8.192 byte, đúng hai khóa `username` và `password`. Khách có thể gọi khi chưa có phiên. Dùng kiểm tra Origin và chính sách IP proxy tin cậy theo #111. |
| Thành công | `201 {"username":"demo.member176","role":"MEMBER"}` sau khi commit. Phản hồi có `Cache-Control: no-store` như các phản hồi đăng ký khác. Việc cấp cookie phiên thuộc `POST /auth/login`. |
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
- [Prototype](story-176-prototype.html) mở trực tiếp, mô phỏng bằng bộ nhớ của tab. Các lựa chọn mô phỏng chuyển trạng thái phục vụ BA, gồm ví dụ danh mục, thời gian chờ và lỗi. Kiểm thử hợp đồng HTTP, cookie, quyền, hash và ghi đồng thời thuộc bản triển khai.


## Ca nghiệm thu bổ sung cho #176

| Mã | Thực hiện | Kết quả |
| --- | --- | --- |
| AC10 | Dùng tên mới hợp lệ, thử lần lượt `abc1234` và `abc123😀` trên form và gọi trực tiếp API với JSON UTF-8, Origin đúng và còn hạn mức. | Cả hai có 7 điểm mã. Form báo **Mật khẩu phải có ít nhất 8 ký tự** tại trường mật khẩu và chặn gửi. API trả 400 `INVALID_INPUT`. SQL Server có 0 dòng cho mỗi tên thử. |
| AC11 | Thử `abc12345` và `abc1234😀` qua form và API với tên mới cho từng lượt. Thử thêm mật khẩu có dấu kết hợp và emoji ghép tại biên 8 điểm mã. | FE và BE đếm từng điểm mã. Các mẫu hợp lệ có đúng 8 điểm mã được chấp nhận. Mỗi lượt thành công trả 201 và lưu một thành viên. |
| AC12 | Thử mật khẩu thiếu, rỗng, 8 dấu cách, surrogate đứng lẻ và JSON có byte UTF-8 lỗi. Thử 256 emoji 😀, rồi thêm một ký tự ASCII. | Form từ chối đầu vào lỗi mà nó nhận được. API trả 400 và không ghi dòng cho dữ liệu sai. Mẫu 1.024 byte được chấp nhận, mẫu 1.025 byte bị từ chối. |
| AC13 | Đăng nhập bằng mật khẩu cũ của tài khoản thử nghiệm đã tồn tại trước triển khai, gồm mẫu dưới 8 điểm mã nếu bộ dữ liệu có fixture tương ứng. Đăng ký tài khoản mới với khoảng trắng biên rồi đăng nhập bằng chuỗi nguyên vẹn. | Tài khoản cũ tiếp tục đăng nhập. Tài khoản mới dùng hash Argon2id và xác minh chuỗi nguyên vẹn. |

### Demo nghiệm thu trên SQL Server

Chuẩn bị schema thử nghiệm Microsoft SQL Server với migration hiện hành, thiết bị tổng hợp và tên mới `demo.member176` (hoặc hậu tố riêng nếu chạy lại). Mở **Đăng ký** từ **Đăng nhập**, gửi `abc123😀` để quan sát lỗi, rồi sửa thành `abc1234😀` và gửi. Kiểm tra xác nhận sau 201, tên điền sẵn khi quay về đăng nhập và ô mật khẩu trống. Tự nhập mật khẩu đã tạo, đăng nhập và mở **Danh mục thiết bị**. Tester đối chiếu bằng truy vấn T-SQL tham số hóa theo tên chuẩn để xác nhận số dòng, vai trò MEMBER và tiền tố Argon2id của hash. Thực hiện riêng lượt POST với mẫu 7 điểm mã để xác nhận HTTP 400 và số dòng bằng 0. Dùng dữ liệu tổng hợp cho toàn bộ các bước.

## Đồng bộ triển khai #176

- FE và BE thống nhất kiểm tra Unicode hợp lệ trước khi đo UTF-8. Duyệt chuỗi theo điểm mã, ví dụ `[...password].length`. Emoji đơn như 😀 tính một điểm mã. Emoji ghép và dấu kết hợp tính theo từng thành phần. Thuộc tính HTML `minlength` đếm theo UTF-16, vì vậy FE dùng kiểm tra tùy chỉnh. FE đo UTF-8 bằng TextEncoder, BE dùng Buffer.byteLength.
- BE xác thực toàn bộ đầu vào trước khi băm và ghi SQL Server. Tái sử dụng Argon2id, lược đồ và khóa duy nhất hiện hành. Triển khai API trước khi phát hành FE với ngưỡng 8 để hai lớp chấp nhận cùng giá trị khi FE mới lên môi trường.
- Prototype mô phỏng các màn và lỗi trong tab. Các kiểm tra API, quyền, cookie, Argon2id và demo trên SQL Server thực hiện khi nghiệm thu bản triển khai.

