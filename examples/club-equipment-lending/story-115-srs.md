# SRS · Xác nhận giao thiết bị

Story #115 · Task BA #133 · Club Equipment Lending

## Phạm vi và tác nhân

Quản lý xác nhận giao thiết bị vật lý cho yêu cầu đã duyệt. Thành viên sở hữu theo dõi trạng thái sau khi tải lại danh sách hoặc chi tiết. Nguồn yêu cầu là Redmine #115 và thiết kế SA task #132 trong `story-115-sa-design.md`. Xác nhận nhận lại thuộc #116.

## Luồng nghiệp vụ

1. Quản lý vào **Yêu cầu đã duyệt** và mở chi tiết. Đây là điểm vào đề xuất cho những yêu cầu đã rời hàng đợi duyệt. Danh sách hiện mã yêu cầu, mã và tên thiết bị, người mượn và giờ đặt. Chi tiết hiện thêm trạng thái; chỉ chi tiết **Đã duyệt** có nút **Xác nhận giao**.
2. Quản lý đối chiếu yêu cầu khi giao thiết bị rồi chọn **Xác nhận giao**. Trong lúc gửi, màn hình báo **Đang xác nhận giao…** và khóa thao tác gửi. Trạng thái hiển thị vẫn là **Đã duyệt** cho tới khi có kết quả đã lưu.
3. Máy chủ kiểm tra phiên, quyền quản lý, CSRF và trạng thái hiện tại. Thiết bị chỉ sẵn giao nếu không có yêu cầu khác cùng ID thiết bị đang ở `HANDED_OVER`. Giờ đặt và người mượn của lượt đang giữ không ảnh hưởng đến phép kiểm tra. Có thể giao ngoài giờ đặt nếu thiết bị rảnh.
4. Khi thành công, một giao dịch SQL Server cập nhật `APPROVED → HANDED_OVER` và ghi một sự kiện gồm mã yêu cầu, trạng thái trước và sau, người thực hiện từ phiên và thời điểm UTC do SQL Server cấp. Sau commit, chi tiết hiện **Đã giao** và thông báo thành công. Khi quay về danh sách đã duyệt, yêu cầu này đã rời danh sách.
5. Thành viên tải lại danh sách hoặc chi tiết của mình để thấy **Đã giao**. Định dạng giờ giao và giờ đặt theo `Asia/Bangkok` (UTC+7) ở nơi dữ liệu tương ứng được hiển thị.

## Ngoại lệ và phản hồi giao diện

| Kết quả | Phản hồi và thao tác |
| --- | --- |
| Danh sách hoặc chi tiết đang tải | Báo đang tải và chưa hiện nút giao. |
| Danh sách rỗng | Quản lý thấy **Chưa có yêu cầu đã duyệt**. Thành viên thấy **Bạn chưa có yêu cầu mượn**. |
| Lỗi tải danh sách hoặc chi tiết | Báo lỗi ngay tại màn hình và cho **Thử tải lại**. |
| `409 EQUIPMENT_IN_USE` | Hiện **Thiết bị vẫn đang được giữ. Hãy xác nhận nhận lại trước khi giao lượt này.** Giữ **Đã duyệt**, không ghi sự kiện giao và không nêu người đang giữ. Sau khi nhận lại được xác nhận, quản lý có thể thử giao lại. |
| `409 INVALID_TRANSITION` | Báo trạng thái đã thay đổi, khóa nút giao và cho tải lại chi tiết để đọc trạng thái hiện tại. |
| `400 INVALID_REQUEST`, `404 NOT_FOUND` | Báo liên kết không hợp lệ hoặc không tìm thấy yêu cầu. Cho quay về danh sách. Chi tiết ngoài quyền sở hữu cũng trả 404. |
| `401 AUTH_REQUIRED` | Yêu cầu đăng nhập lại. Khi quay lại chi tiết, tải trạng thái mới trước khi cho giao. |
| `403 FORBIDDEN`, `403 CSRF_INVALID` | Báo thiếu quyền hoặc không xác thực được thao tác. Khóa nút giao trong lượt hiển thị hiện tại. Với CSRF, khôi phục token theo cơ chế #111 trước khi cho gửi lại. |
| `500 INTERNAL_ERROR`, mất kết nối hoặc mất phản hồi | Báo chưa xác định được kết quả. Chỉ cho tải lại chi tiết. Nếu đã giao, hiển thị trạng thái đã lưu. Nếu vẫn đã duyệt, cho thử giao lại. Nếu tải lại lỗi, giữ nút giao bị khóa và cho thử tải lại. |

## Tiêu chí nghiệm thu

| Mã | Điều kiện và kết quả quan sát được |
| --- | --- |
| AC1 | Với quản lý có phiên và CSRF hợp lệ, mở một yêu cầu đã duyệt từ danh sách đã duyệt. Khi giao thiết bị rảnh, API trả 200 sau commit và chi tiết hiện **Đã giao**. CSDL có đúng một sự kiện chuyển trạng thái với actor của phiên và thời điểm do SQL Server cấp. Áp dụng cả trước giờ bắt đầu và sau giờ kết thúc đặt. |
| AC2 | Thành viên sở hữu thấy **Đã giao** sau khi tải lại danh sách và chi tiết. Thành viên khác nhận 404 khi đọc trực tiếp chi tiết. Gọi trực tiếp lệnh giao bằng phiên thành viên nhận 403, thiếu phiên nhận 401, quản lý thiếu CSRF hợp lệ nhận 403. Các lần bị từ chối không ghi dữ liệu. |
| AC3 | Chuẩn bị hai yêu cầu đã duyệt sát biên cho cùng thiết bị. Giao lượt đầu rồi thử giao lượt sau khi lượt đầu đã quá giờ đặt nhưng chưa được nhận lại. Lượt sau nhận `EQUIPMENT_IN_USE`, UI nêu lý do, yêu cầu vẫn **Đã duyệt**, không có sự kiện giao mới. Thiết bị vật lý khác vẫn có thể được giao. Khi #116 đã commit nhận lại và thiết bị rảnh, giao lại lượt sau thành công. |
| AC4 | Thử ID không hợp lệ, ID không tồn tại và yêu cầu ở các trạng thái `PENDING`, `REJECTED`, `HANDED_OVER`, `RETURNED`. API lần lượt trả 400, 404 hoặc 409 theo bảng ngoại lệ, dữ liệu và lịch sử không đổi. |
| AC5 | Gửi đồng thời hai lệnh hợp lệ cho hai yêu cầu đã duyệt của cùng thiết bị rảnh trên hai kết nối SQL Server, với giao dịch thắng commit và chưa có lệnh nhận lại. Một thành công, một nhận `EQUIPMENT_IN_USE`. Nếu hai lệnh cùng ID, một thành công và một nhận `INVALID_TRANSITION`. Mỗi ca chỉ có một yêu cầu giữ thiết bị và một sự kiện giao mới. |
| AC6 | Buộc ghi sự kiện thất bại sau bước cập nhật trạng thái. Rollback giữ yêu cầu **Đã duyệt** và số sự kiện giao không đổi. Mô phỏng mất phản hồi trước hoặc sau commit và kiểm tra giao diện tải lại chi tiết trước khi cho gửi lại, theo kết quả thực tế. |
| AC7 | Kiểm tra danh sách và chi tiết ở trạng thái đang tải, lỗi đọc và thử lại, cùng danh sách rỗng ở hai vai trò. Khi đang xác nhận, thao tác gửi lặp từ giao diện bị khóa. |

## Điểm FE/BE cần thống nhất khi tích hợp

- Đối chiếu #111 cho phiên, CSRF và đường đăng nhập lại. Lệnh `POST /loan-requests/{id}/handover` gửi cookie phiên cùng `X-CSRF-Token`, không cần payload. Dùng trường `code` để chọn thông báo giao diện.
- Chốt đường đọc danh sách quản lý lọc `APPROVED` và đường chi tiết theo hợp đồng #114, gồm DTO cho mã thiết bị, người mượn và giờ đặt. Phản hồi 200 theo DTO #114 có `status: "HANDED_OVER"`. Người giao và thời điểm giao lưu ở nhật ký nội bộ theo thiết kế SA. Đối chiếu đường đọc #113 để danh sách và chi tiết thành viên cùng nhận trạng thái mới.
- Đối chiếu migration #112–114 với thiết kế SA. Giao, duyệt và nhận lại dùng cùng thứ tự khóa thiết bị rồi yêu cầu. Chỉ mục unique có điều kiện bảo vệ tối đa một yêu cầu `HANDED_OVER` mỗi thiết bị, sau khi kiểm tra dữ liệu hiện có. Đối chiếu #116 khi kiểm thử cạnh tranh giao và nhận lại.
- Tích hợp cần kết quả #112–114 cho dữ liệu yêu cầu, lịch và đường đọc quản lý/thành viên. Ca giao sau nhận lại phụ thuộc #116. Prototype độc lập dùng dữ liệu giả và phản hồi mô phỏng. Các kiểm tra quyền API và giao dịch SQL Server chạy khi có bản tích hợp.

## Hướng dẫn xem prototype

Mở `story-115-prototype.html` trực tiếp. Từ **Yêu cầu đã duyệt**, mở YC-026 và xác nhận giao để thấy xung đột với lượt trước đã quá hạn. Tại **Dữ liệu thử**, chọn **Thiết bị đã rảnh** để nạp dữ liệu mẫu sau khi lượt trước đã được nhận lại. Giao lại và quay về danh sách quản lý để thấy YC-026 đã rời danh sách. Chuyển sang **Thành viên** để thấy **Đã giao** trong danh sách và chi tiết YC-026. Các nút dữ liệu thử cũng mô phỏng danh sách rỗng, lỗi tải, yêu cầu đổi trạng thái và mất phản hồi trước hoặc sau khi lưu. Mỗi nút dữ liệu thử nạp lại bộ dữ liệu riêng. Tải lại toàn bộ tệp sẽ khôi phục dữ liệu ban đầu.
