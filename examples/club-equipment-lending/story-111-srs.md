# SRS · Nền tảng đăng nhập, phân quyền và dữ liệu mẫu

Story #111 · Task BA #118 · Club Equipment Lending

Nguồn đối chiếu gồm Redmine #111 và #118 qua MCP Lending và [thiết kế SA #117](story-111-sa-design.md).

## Phạm vi và quy tắc

- Khách được mở màn đăng nhập. Đường dẫn nghiệp vụ trực tiếp đưa khách về đăng nhập. API nghiệp vụ yêu cầu phiên hợp lệ và trả `401` nếu thiếu, hết hạn hoặc đã thu hồi phiên.
- Thành viên và quản lý đều xem danh mục thiết bị sau khi đăng nhập. Trang danh mục hiển thị tên, mã thiết bị và vai trò hiện tại. Điều hướng quản lý chỉ hiện với quản lý. API kiểm tra quyền từ phiên phía máy chủ cho mọi lệnh quản lý, trước khi tra cứu đối tượng. Thành viên có phiên và CSRF hợp lệ nhận `403` khi gọi trực tiếp lệnh quản lý, kể cả với ID không tồn tại.
- Đăng nhập dùng tài khoản cục bộ. Hai tài khoản demo/test là `demo.member` (`MEMBER`) và `demo.manager` (`MANAGER`). Mật khẩu seed lấy từ cấu hình demo/test và băm Argon2id. Chạy lại seed theo tên đăng nhập và mã tài sản, giữ duy nhất một bản ghi cho mỗi khóa. Chỉ bật seed trong demo/test.
- Danh mục mẫu gồm hai máy chiếu cùng tên, mã `DEMO-01` và `DEMO-02`, có hai ID riêng. Mỗi ID định danh một thiết bị vật lý và lịch của chính thiết bị đó. Lịch ban đầu trống. Story #112 cung cấp API tra cứu lịch. Prototype minh họa chuyển lịch theo thiết bị bằng dữ liệu cố định.
- Story #111 cung cấp lớp kiểm tra quyền quản lý. Kiểm thử lớp này trong #111 bằng bộ kiểm thử tích hợp với handler thử nghiệm có theo dõi việc thực thi. Stories #114–116 kiểm lại qua endpoint duyệt, từ chối, giao và nhận thực tế. Gửi yêu cầu thuộc #113. Quy tắc chỉ một yêu cầu trùng giờ được duyệt cho cùng thiết bị thuộc #114.

## Luồng màn hình và ngoại lệ

| Màn hình / tình huống | Phản hồi và hành động |
|---|---|
| Mở trang nghiệp vụ | FE kiểm tra phiên, hiển thị trạng thái đang tải. Phiên hợp lệ mở danh mục hoặc màn quản lý nếu có quyền. Khi chưa có phiên, mở đăng nhập. Sau đăng nhập thành công, mở danh mục. |
| Đăng nhập | Tên đăng nhập và mật khẩu bắt buộc. Báo thiếu tại trường tương ứng. Trong khi gửi, khóa nút gửi. Khi sai thông tin, dùng chung thông báo cho tên hoặc mật khẩu sai. Giữ tên đăng nhập và xóa mật khẩu khi gửi thất bại. |
| Giới hạn số lần thử / lỗi mạng lúc đăng nhập | Hiển thị thông báo thử lại sau khi bị giới hạn. Với lỗi kết nối hoặc lỗi máy chủ, báo chưa thể đăng nhập và cho gửi lại. |
| Danh mục đang tải / có dữ liệu | Hiện trạng thái đang tải đến khi có phản hồi. Khi có dữ liệu, hiển thị tên và mã cho từng thiết bị. |
| Danh mục rỗng / lỗi tải | `200` với danh sách rỗng hiển thị “Chưa có thiết bị”. Lỗi kết nối hoặc lỗi máy chủ hiển thị “Không tải được danh mục” và nút “Thử lại”. |
| Phiên hết hạn | Khi API nghiệp vụ trả `401`, xóa thông tin phiên và dữ liệu nghiệp vụ trên FE, về đăng nhập với thông báo phiên hết hạn nếu trước đó đã đăng nhập. |
| Thành viên mở màn quản lý | Hiển thị “Bạn không có quyền truy cập” và liên kết về danh mục. Lỗi `403` giữ phiên hiện tại. |
| Đăng xuất | Khi thành công, BE thu hồi phiên và xóa cookie. FE xóa dữ liệu phiên và về đăng nhập. Nếu yêu cầu lỗi mạng hoặc lỗi máy chủ, báo chưa xác nhận được đăng xuất và cho thử lại. Nếu phiên đã mất, về đăng nhập. |

## Tiêu chí nghiệm thu

| Mã | Điều kiện và kết quả cần kiểm |
|---|---|
| AC01 | Chạy seed demo/test hai lần. Vẫn có đúng một bản ghi cho mỗi tài khoản và mỗi mã mẫu. Đăng nhập lần lượt bằng hai tài khoản, xác nhận vai trò từ `GET /auth/me` và điều hướng tương ứng. |
| AC02 | Với mỗi vai trò, `GET /equipment` trả hai bản ghi máy chiếu mẫu cùng tên, khác mã và khác ID. Khi #112 sẵn sàng, thêm fixture chiếm lịch cho ID thứ nhất và xác nhận cùng cửa sổ tra cứu của ID thứ hai vẫn trống. |
| AC03 | Mở trực tiếp danh mục và màn quản lý khi chưa có phiên, xác nhận được đưa về đăng nhập. Gọi trực tiếp `GET /equipment` với cookie thiếu hoặc hết hạn, nhận `401` và không có dữ liệu thiết bị. |
| AC04 | Dùng phiên thành viên và CSRF hợp lệ gọi handler được bảo vệ bằng lớp quyền quản lý. Nhận `403` và xác nhận handler không chạy. Dùng phiên quản lý và CSRF hợp lệ, handler được thực thi. Kiểm lại tại các endpoint thực tế khi #114–116 triển khai. |
| AC05 | Đăng xuất thành công, sau đó gửi lại cookie phiên cũ tới `GET /equipment`. Nhận `401`. Mở lại màn nghiệp vụ và xác nhận giao diện yêu cầu đăng nhập. |
| AC06 | Thử tên sai và mật khẩu sai, xác nhận cùng mã lỗi và thông báo. Mô phỏng phản hồi chậm, danh sách rỗng và lỗi tải. Xác nhận ba trạng thái tương ứng, nút thử lại khôi phục danh mục khi API hoạt động. |

## Điểm FE và BE cần chốt trước khi tích hợp

| Hạng mục | Hợp đồng từ SA và điểm cần chốt |
|---|---|
| Phiên | `POST /auth/login` nhận `username`, `password`. Đăng nhập và `GET /auth/me` trả `200` với `id`, `username`, `role` và token CSRF. `POST /auth/logout` trả `204`. Chốt tên trường token, tên header CSRF và thời hạn phiên. |
| Bảo vệ API | Cookie phiên `HttpOnly`, `Secure`, `SameSite=Lax`. BE kiểm tra origin khi đăng nhập và CSRF gắn phiên cho lệnh ghi sau đăng nhập. FE dùng cookie cùng origin. Chốt mã lỗi CSRF và cách FE xử lý. |
| Danh mục | `GET /equipment` trả `200` với danh sách có `id`, `asset_code`, `name`. Chốt cấu trúc JSON ngoài cùng. FE dùng `id` khi liên kết lịch và hiển thị `asset_code` để phân biệt hai máy cùng tên. |
| Lỗi | BE trả `code` ổn định. Thiếu phiên trả `401`, thiếu quyền trả `403`, đầu vào sai trả `400` theo thiết kế SA. Chốt mã và HTTP status cho sai thông tin đăng nhập và giới hạn số lần thử, cùng thông tin thời gian thử lại nếu có. |
| Lịch | #112 tra cứu bằng ID thiết bị, hiển thị theo `Asia/Bangkok`. Các cửa sổ dùng khoảng nửa mở `[start, end)`. Chốt fixture và cửa sổ giờ dùng để kiểm tra hai lịch độc lập khi #112 sẵn sàng. |

## Duyệt prototype

Mở [prototype HTML](story-111-prototype.html) trực tiếp trong trình duyệt. Nút điền mẫu dùng tài khoản và mật khẩu tổng hợp của prototype. Thử vào thẳng màn quản lý lần lượt khi chưa đăng nhập, khi là thành viên và khi là quản lý. Bảng mô phỏng cho phép xem phản hồi lớp quyền, chuyển trạng thái tải danh mục và làm hết phiên. Chọn từng thiết bị để xem lịch minh họa của #112. Prototype chạy cục bộ trong bộ nhớ. Mọi phản hồi HTTP hiển thị là mô phỏng. Kiểm thử cookie, API, seed và phân quyền phía máy chủ thuộc bản triển khai.
