# SRS · Gửi và theo dõi yêu cầu mượn

Story #113 · Task BA #129 · Căn cứ Redmine #113 và thiết kế SA #128.

## Phạm vi và luồng sử dụng

Thành viên đã đăng nhập mở **Yêu cầu của tôi**, xem danh sách và mở chi tiết hoặc chọn **Gửi yêu cầu**. Từ lịch #112, giao diện có thể điền trước thiết bị và khoảng giờ để thành viên kiểm tra, chỉnh sửa rồi gửi. Thành viên chọn từng thiết bị vật lý theo tên và mã tài sản. Hai mốc đều bắt buộc và hiển thị theo giờ CLB (Asia/Bangkok, UTC+7). Cho phép mượn qua ngày. Khoảng giờ có dạng [bắt đầu, kết thúc).

Sau khi lưu, mở chi tiết với thông báo **Đã gửi yêu cầu** và nhãn **Chờ duyệt**. Mỗi lần gửi hợp lệ tạo một yêu cầu riêng. Hai yêu cầu trùng giờ cùng thiết bị đều được ghi nhận. Việc giữ lịch khi duyệt thuộc #114. Các thao tác quản lý giao và nhận lại thuộc #115–116.

Danh sách đầy đủ của thành viên hiển thị mã yêu cầu, tên và mã thiết bị, giờ bắt đầu và kết thúc, trạng thái. Sắp xếp theo thời điểm tạo giảm dần rồi theo ID giảm dần. Chi tiết hiển thị thêm thời điểm gửi. Khi mở hoặc tải lại danh sách hay chi tiết, đọc trạng thái hiện hành từ API.

| Mã API | Nhãn hiển thị |
| --- | --- |
| PENDING | Chờ duyệt |
| APPROVED | Đã duyệt |
| REJECTED | Đã từ chối |
| HANDED_OVER | Đã giao |
| RETURNED | Đã trả |

## Ngoại lệ và trạng thái giao diện

| Tình huống | Phản hồi |
| --- | --- |
| Đang đọc danh sách, chi tiết hoặc danh mục | Hiện trạng thái tải. Chỉ hiện rỗng sau phản hồi thành công. |
| Danh sách rỗng | Hiện “Bạn chưa có yêu cầu nào” và dẫn đến form. |
| Danh mục rỗng | Hiện “Chưa có thiết bị để chọn” và vô hiệu hóa nút gửi. |
| Thiếu trường, giờ sai hoặc giờ kết thúc bằng/trước giờ bắt đầu | Hiện lỗi gần trường liên quan, giữ dữ liệu đã nhập và chuyển focus đến trường lỗi đầu tiên. BE kiểm tra lại và trả 400 khi dữ liệu sai. |
| Thiết bị không còn tồn tại | Hiện lỗi tại ô thiết bị, tải lại danh mục, yêu cầu chọn lại và giữ giờ đã nhập. |
| Đang gửi | Hiện “Đang gửi…” và khóa trường nhập cùng nút gửi đến khi có kết quả. |
| Mất phản hồi POST hoặc lỗi máy chủ khi gửi | Hiện “Chưa xác nhận được kết quả. Hãy kiểm tra danh sách trước khi gửi lại”. Giữ giờ và thiết bị đã nhập trong form, cung cấp đường về danh sách. |
| Không đọc được dữ liệu | Hiện lỗi và nút thử lại trên màn liên quan. Khi thiếu tên từ danh mục nhưng đã đọc được yêu cầu, hiển thị ID thiết bị làm dự phòng. |
| Phiên hết hạn hoặc thiếu | Yêu cầu đăng nhập lại theo luồng #111. |
| Sai vai trò hoặc token CSRF không hợp lệ | Hiện thông báo theo mã lỗi. Với CSRF, hướng dẫn tải lại trang để lấy token phiên trước khi gửi lại. |
| Chi tiết thuộc người khác hoặc ID hợp lệ chưa tồn tại | Cùng hiện “Không tìm thấy yêu cầu” và đường về danh sách. |

## Tiêu chí nghiệm thu

| Mã | Thao tác với dữ liệu tổng hợp | Kết quả |
| --- | --- | --- |
| AC01 | Gửi thiết bị hợp lệ lúc 09:00–10:00 ngày 16/11/2026 theo giờ CLB | HTTP 201, có Location, ID mới và PENDING. Chi tiết xác nhận đã gửi và hiển thị 09:00–10:00. Dữ liệu UTC lần lượt là 02:00 và 03:00. |
| AC02 | Thử để trống, đặt hai mốc bằng nhau hoặc đảo chiều. Gọi API với ngày sai, thiếu offset hoặc hai thời điểm bằng nhau sau quy đổi UTC. Gửi thử khoảng hợp lệ qua nửa đêm. | Trường nhập sai có thông báo phù hợp. API trả 400 và không tạo hàng cho payload sai. Khoảng hợp lệ qua nửa đêm nhận 201. |
| AC03 | Hai thành viên gửi khoảng 09:00–10:00 và 09:30–10:30 cho cùng thiết bị | Cả hai nhận 201 với ID khác nhau và PENDING. Mỗi người chỉ thấy yêu cầu của mình. Lịch #112 vẫn trống nếu chưa có yêu cầu chiếm lịch. |
| AC04 | Thành viên mở danh sách và từng chi tiết có dữ liệu mẫu ở năm trạng thái. Cập nhật trạng thái ở nguồn dữ liệu kiểm thử rồi tải lại. | Đủ trường hiển thị, nhãn đúng theo bảng, sắp xếp ổn định cả khi trùng thời điểm tạo và đọc được trạng thái mới. |
| AC05 | Dùng phiên A mở URL giao diện và gọi API chi tiết của B. Lặp lại với ID dương chưa tồn tại. | Cùng phản hồi 404 và cùng nội dung lỗi. Phản hồi không tiết lộ dữ liệu yêu cầu của B. |
| AC06 | Kiểm tra thiếu phiên, sai vai trò, CSRF thiếu/sai và payload chứa borrower_id hoặc status | Lần lượt 401, 403 FORBIDDEN, 403 CSRF_INVALID và 400 INVALID_INPUT. Không tạo hàng. |
| AC07 | Làm chậm hoặc làm lỗi lượt đọc, thử danh sách trống, thiết bị bị xóa và giả lập mất phản hồi sau khi gửi | UI theo bảng ngoại lệ. Tải lại hoặc thử lại lượt đọc được. Khi kết quả gửi chưa rõ, người dùng có thể kiểm tra danh sách trước khi gửi lại. |

## FE và BE đối chiếu trước tích hợp

- Dùng các tuyến cùng origin. `GET /equipment` lấy tên và mã tài sản. `POST /loan-requests` chỉ gửi `equipment_id`, `start_at`, `end_at` cùng header `X-CSRF-Token`. `GET /loan-requests` trả mảng và `GET /loan-requests/{id}` trả một đối tượng. FE thống nhất URL màn chi tiết riêng với tuyến API và nối luồng đăng nhập/token của #111.
- Đối tượng trả về gồm `id`, `equipment_id`, `start_at`, `end_at`, `created_at`, `status`. FE gửi ISO 8601 có giây và offset rõ ràng, tối đa ba chữ số phần giây. FE hiển thị các mốc UTC trả về theo Asia/Bangkok kể cả khi thiết bị người dùng đặt múi giờ khác.
- BE xác thực phiên, vai trò MEMBER, CSRF với POST, đầu vào rồi mới truy cập đối tượng. Lỗi có dạng `{"code":"NOT_FOUND"}`. ID là số nguyên dương trong miền SQL Server int. Kiểm tra ngày giờ thực và miền datetime2(3) sau đổi UTC. Phản hồi dùng `Cache-Control: no-store`.
- BE lấy người mượn từ phiên và đặt PENDING khi ghi. Cả hai tuyến đọc luôn lọc theo người mượn. Dùng Microsoft SQL Server và T-SQL tham số hóa. Trước triển khai, đối chiếu migration `loan_requests` và chỉ mục của #112 đã tích hợp. Hai bên thống nhất tham số điền sẵn từ màn lịch khi nối #112.
- FE phân biệt `404 NOT_FOUND` theo thao tác. Khi gửi, mã này báo thiết bị không tồn tại. Khi đọc chi tiết, mã này dùng chung cho yêu cầu ngoài quyền và yêu cầu chưa tồn tại. Với `400 INVALID_INPUT`, FE giữ bản nháp và hiện lỗi chung nếu API chỉ trả mã lỗi. Với `500 INTERNAL_ERROR`, FE áp dụng cách thử lại hoặc kiểm tra kết quả tương ứng với thao tác đọc hay gửi.

## Cách xem prototype

Mở `story-113-prototype.html` trực tiếp trên trình duyệt. Thanh mô phỏng cho phép đổi trạng thái tải, rỗng, lỗi và thử URL ngoài quyền. Gửi hai lượt trùng giờ tại kịch bản bình thường để thấy hai mã riêng. Dữ liệu là giả lập trong bộ nhớ và làm mới khi tải lại tệp. Kiểm thử quyền sở hữu, CSRF và lưu SQL Server cần thực hiện trên bản tích hợp.
