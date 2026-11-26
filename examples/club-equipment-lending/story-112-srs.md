# SRS #112 · Xem thiết bị và lịch trống

Task BA #126. Căn cứ tiêu chí Redmine #112, bàn giao #111 và [thiết kế SA #125](story-112-sa-design.md).

## Phạm vi và luồng sử dụng

1. Thành viên đã đăng nhập mở danh mục #111 và chọn xem lịch của một thiết bị. Quản lý đã đăng nhập có cùng quyền tra cứu theo thiết kế SA. Màn lịch chọn sẵn thiết bị vừa mở và cho phép đổi thiết bị bằng danh mục. Mỗi lựa chọn hiển thị tên và mã tài sản, dùng ID vật lý để tra cứu.
2. Người dùng nhập ngày giờ bắt đầu và kết thúc theo giờ CLB **Asia/Bangkok (UTC+07:00)**. Hiển thị nhãn múi giờ cạnh bộ nhập và cạnh kết quả. Thiết kế UI dùng độ chính xác đến phút khi nhập, cho phép qua ngày. Kết quả giữ giây và phần giây khi mốc trả về có độ chính xác đó.
3. Người dùng nhấn **Xem lịch trống**. Khi thiếu trường hoặc giờ kết thúc không sau giờ bắt đầu, báo lỗi cạnh trường tương ứng và chuyển tiêu điểm đến trường sai đầu tiên. Giữ lựa chọn để người dùng sửa. Với đầu vào hợp lệ, báo đang tải đến khi có phản hồi.
4. Hiển thị danh sách khoảng trống theo thứ tự tăng dần. Mỗi hàng hiển thị ngày và giờ của cả hai mốc để đọc được khoảng qua ngày. Kết quả ghi thiết bị, cửa sổ đã tra cứu và thời điểm cập nhật. Khi đổi bất kỳ đầu vào nào, xóa kết quả cũ và yêu cầu tra cứu lại. Phản hồi của các lượt đã bị thay thế không cập nhật màn hình.
5. Người dùng có thể đổi khoảng, tra cứu lại hoặc quay về danh mục. Lịch phản ánh giờ đặt tại thời điểm đọc và có thể thay đổi sau đó. Gửi yêu cầu, duyệt, giao và trả thuộc #113–116.

## Quy tắc nghiệp vụ

- Cửa sổ và giờ đặt là khoảng nửa mở `[bắt đầu, kết thúc)`. Hai khoảng giao nhau khi đầu khoảng này trước cuối khoảng kia và cuối khoảng này sau đầu khoảng kia. Khoảng chỉ chạm biên nằm ngoài phần giao.
- Chỉ `APPROVED` và `HANDED_OVER` chiếm lịch của đúng thiết bị theo giờ đặt. `PENDING`, `REJECTED`, `RETURNED` đều bỏ qua. Trạng thái giữ thiết bị thực tế được kiểm tra ở #115.
- Cắt các khoảng bận theo cửa sổ, gộp phần bận giao nhau hoặc nối tiếp, rồi trả phần còn lại có độ dài dương. Nếu toàn bộ cửa sổ trống, trả đúng một khoảng bằng cửa sổ. Nếu toàn bộ cửa sổ bận, trả mảng rỗng.
- Màn hình và phản hồi lịch chỉ chứa ngữ cảnh tra cứu và thời gian. Tên, ID người mượn, ID yêu cầu, trạng thái và chi tiết từng yêu cầu đều nằm ngoài dữ liệu trả về.

## Trạng thái và ngoại lệ

| Tình huống | Hành vi giao diện |
| --- | --- |
| Đang tải danh mục | Thông báo đang tải, khóa bộ tra cứu. |
| Danh mục rỗng | Báo “Chưa có thiết bị để tra cứu”, khóa bộ tra cứu. |
| Danh mục lỗi | Báo không tải được danh mục, có nút thử lại. |
| Đang tải lịch | Xóa kết quả cũ, thông báo đang tải. Cho phép sửa đầu vào và tra cứu mới. |
| Lịch bận toàn bộ | Hiển thị ngữ cảnh và “Không có khung giờ trống trong khoảng đã chọn”. |
| `400 INVALID_INPUT` | Yêu cầu kiểm tra thiết bị và ngày giờ. Giữ dữ liệu nhập để sửa. |
| `401 AUTH_REQUIRED` khi mở màn hoặc tra cứu | Xóa dữ liệu lịch, dùng luồng đăng nhập #111. |
| `403 FORBIDDEN` | Xóa dữ liệu lịch và báo tài khoản thiếu quyền. |
| `404 NOT_FOUND` | Báo thiết bị không còn khả dụng. Cho tải lại danh mục và chọn thiết bị hiện có. |
| `500 INTERNAL_ERROR` hoặc mất kết nối | Báo chưa tải được lịch, giữ dữ liệu nhập và cho thử lại với cùng lựa chọn. |

Thông báo tải và kết quả dùng vùng thông báo lịch sự cho trình đọc màn hình. Các trường có nhãn, nút và trường nhập thao tác được bằng bàn phím. Bố cục một cột khi màn hình hẹp.

## Tiêu chí nghiệm thu

Dữ liệu tổng hợp ngày 16/11/2026, giờ CLB. Hai máy chiếu cùng tên mang mã DEMO-01 và DEMO-02. Chỉ DEMO-01 có dữ liệu sau.

| Trạng thái | Giờ đặt |
| --- | --- |
| Đã duyệt | 08:30–10:00 |
| Đã giao | 10:00–11:00 |
| Đã duyệt | 07:00–09:00 và 13:00–14:00 |
| Chờ duyệt | 11:00–11:30 |
| Đã từ chối | 11:30–12:00 |
| Đã trả | 12:00–13:00 |

| Mã | Thao tác và kết quả mong đợi |
| --- | --- |
| AC1 | Chọn DEMO-01, tra 09:00–13:00. Chỉ có 11:00–13:00. Hai lượt bận nối tiếp không sinh khoảng trống 0 phút, hai lượt chạm biên cửa sổ không chiếm lịch trong cửa sổ, ba trạng thái còn lại không chiếm đoạn 11:00–13:00. |
| AC2 | Cùng cửa sổ, đổi sang DEMO-02. Nhận một khoảng 09:00–13:00. |
| AC3 | Tra DEMO-01 từ 09:00 đến 11:00. API trả `200` và mảng rỗng, UI báo bận toàn bộ. Danh mục rỗng và lỗi tải có thông báo riêng. |
| AC4 | Đặt múi giờ máy khách khác Bangkok. Tra DEMO-01 từ 09:00 đến 13:00. Hai mốc gửi tương đương 02:00Z và 06:00Z. UI hiển thị 11:00–13:00 với nhãn giờ CLB. Tra khoảng qua đêm trên DEMO-02 và kiểm tra ngày ở cả hai đầu. |
| AC5 | Nhập thiếu mốc, trùng mốc hoặc đảo chiều. UI báo lỗi và không gửi. Với phiên hợp lệ, truy cập API trực tiếp với ngày không hợp lệ, mốc thiếu offset, tham số lặp hoặc ID sai định dạng nhận `400`. |
| AC6 | Đổi thiết bị hoặc mốc giờ trong lúc tải, gửi lượt mới rồi để phản hồi cũ về sau. Chỉ kết quả lượt mới xuất hiện. Mô phỏng lỗi mạng/500 rồi thử lại để thấy lịch tải thành công. |
| AC7 | Gọi API không có phiên hoặc với phiên hết hạn nhận `401`, vai trò ngoài tập cho phép nhận `403`. Thiết bị không tồn tại với phiên hợp lệ nhận `404`. UI xử lý theo bảng ngoại lệ. |
| AC8 | Tra bằng thành viên và quản lý với cùng fixture. Cả hai có cùng giờ trống và không thấy thông tin người mượn trong API hoặc UI. Đổi fixture từ `HANDED_OVER` sang `RETURNED` rồi tra lại, khoảng tương ứng được giải phóng. |
| AC9 | Tra DEMO-01 từ 06:00 đến 15:00. Hai lượt đã duyệt chồng nhau và lượt đã giao nối tiếp tạo một khối bận 07:00–11:00. Kết quả theo thứ tự là 06:00–07:00, 11:00–13:00 và 14:00–15:00. |

## Bàn giao FE và BE

- FE giữ hợp đồng `GET /equipment` và phiên #111. Gọi `GET /equipment/{id}/availability?from=…&to=…` cùng origin. Chuyển mốc nhập theo Asia/Bangkok, độc lập múi giờ máy khách. Gửi ISO 8601 có giây và múi giờ, dùng UTC `Z` hoặc offset có dấu cộng được mã hóa. Khi hiển thị, định dạng rõ timezone từ hợp đồng.
- BE xác thực phiên trước khi kiểm tra dữ liệu và chỉ cho `MEMBER`/`MANAGER`. Mỗi tham số thời gian xuất hiện đúng một lần. Kiểm tra ngày giờ, tối đa ba chữ số phần giây, miền UTC `datetime2(3)`, thứ tự hai mốc và ID số nguyên dương trong miền `int` SQL Server.
- Hai bên đối chiếu payload thành công gồm `equipment_id`, `timezone` (Asia/Bangkok), `as_of` (giờ UTC máy chủ ghi sau khi đọc) và `available` (mảng cặp `start_at`/`end_at` UTC). Lỗi dùng `{"code":"…"}` theo bảng trên. BE dùng `Cache-Control: no-store` cho lịch.
- BE áp dụng migration Microsoft SQL Server sau `001-foundation.sql`, dùng T-SQL tham số hóa và fixture tổng hợp theo thiết kế #125. Tích hợp định tuyến Caddy cho API lịch. FE và BE chạy đối chiếu AC1–AC9 trên bản tích hợp.

## Dùng prototype

Mở trực tiếp [story-112-prototype.html](story-112-prototype.html). Chọn **Xem lịch** ở danh mục tổng hợp để mở bộ tra cứu. Bộ nhập điền sẵn ngày và giờ của AC1 để thử ngay. Khu vực **Điều khiển mô phỏng** đổi trạng thái danh mục và phản hồi tiếp theo. Lựa chọn lỗi lịch chỉ có hiệu lực một lần để có thể thử lại. Chọn phiên hết hạn để đi qua màn đăng nhập mô phỏng. Prototype dùng thời gian và thiết bị tổng hợp, phản hồi qua bộ hẹn giờ trong trình duyệt.
