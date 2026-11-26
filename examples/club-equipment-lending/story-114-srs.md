# SRS · Duyệt hoặc từ chối yêu cầu mượn

Story #114 · Task BA #131 · Căn cứ Redmine #114/#131 qua MCP Lending và thiết kế SA #130.

## Phạm vi và quy tắc nghiệp vụ

- Quản lý (`MANAGER`) xem toàn bộ yêu cầu đang chờ của CLB, mở chi tiết và quyết định từng yêu cầu. Hàng đợi sắp theo thời điểm gửi tăng dần, rồi theo ID tăng dần.
- Mỗi yêu cầu hiển thị mã yêu cầu, tên và mã thiết bị vật lý, tài khoản người gửi, giờ bắt đầu và kết thúc, thời điểm gửi và trạng thái. Hiển thị giờ CLB theo `Asia/Bangkok` (UTC+7), kèm ngày ở cả hai mốc khi qua ngày.
- Duyệt chuyển `PENDING → APPROVED` và chiếm lịch sau commit. Từ chối chuyển `PENDING → REJECTED` dù khoảng giờ có xung đột. Hai lệnh dùng xác nhận trước khi gửi. Lý do từ chối nằm ngoài hợp đồng hiện tại.
- Hai yêu cầu chờ có thể cùng trùng giờ. Khi duyệt, chỉ `APPROVED` và `HANDED_OVER` của cùng thiết bị chiếm lịch. Hai khoảng giao nhau khi bắt đầu của mỗi khoảng nhỏ hơn kết thúc của khoảng kia. Khoảng nửa mở `[bắt đầu, kết thúc)` cho phép hai lượt sát biên.
- Microsoft SQL Server và T-SQL tuần tự hóa chuyển trạng thái theo ID thiết bị. Kiểm tra trạng thái nguồn và giao lịch dưới khóa theo thiết kế SA. Cập nhật trạng thái và ghi sự kiện gồm người thao tác, trạng thái nguồn/đích và thời điểm UTC trong cùng giao dịch.
- Thành viên xem yêu cầu của mình qua #113. Lịch #112 phản ánh trạng thái đã commit. Giao và nhận lại thuộc #115–116.

## Luồng và ngoại lệ

| Tình huống | Hành vi quan sát được |
| --- | --- |
| Mở hàng đợi hoặc chi tiết | Có thông báo đang tải. Hàng đợi rỗng hiển thị “Chưa có yêu cầu đang chờ”. Lỗi đọc hiển thị thông báo và nút thử lại. |
| Chọn hành động | Xác nhận hiển thị mã yêu cầu, thiết bị và giờ mượn. Hủy xác nhận giữ nguyên hàng đợi. Trong khi gửi, khóa cả hai hành động trên yêu cầu đó để tránh gửi lặp. |
| POST 200 | Hiện kết quả, bỏ dòng khỏi hàng đợi sau khi nhận phản hồi, cập nhật chi tiết nếu đang mở và đưa tiêu điểm về vị trí thích hợp nếu dòng biến mất. |
| 409 `SCHEDULE_CONFLICT` | Báo thiết bị đã có lịch đè lên khung giờ. Làm mới hàng đợi, giữ thông báo gắn với dòng nếu vẫn chờ và cho phép từ chối sau khi xác nhận lại trạng thái. |
| 409 `INVALID_TRANSITION` | Báo yêu cầu đã đổi trạng thái, tải lại chi tiết và hàng đợi. Chỉ bật hành động nếu dữ liệu mới xác nhận yêu cầu đang chờ. |
| 401 `AUTH_REQUIRED` | Báo phiên đã hết hiệu lực, đưa người dùng về luồng đăng nhập của #111. |
| 403 `FORBIDDEN` / `CSRF_INVALID` | Báo thiếu quyền hoặc phiên thao tác cần làm mới tương ứng. Dùng cơ chế phiên/CSRF của #111 trước khi nhận lệnh mới. |
| 400 `INVALID_INPUT` / 404 `NOT_FOUND` | Báo đường dẫn sai hoặc yêu cầu không còn truy cập được. Cho quay lại và làm mới hàng đợi. |
| 500 `INTERNAL_ERROR`, timeout hoặc mất mạng khi ghi | Báo chưa xác định được kết quả, khóa thao tác trên dòng, đọc lại chi tiết rồi đồng bộ hàng đợi. Nếu vẫn đọc lỗi, cho thử tải lại trạng thái. Nếu đã có trạng thái cuối, hiện trạng thái thực tế. Nếu vẫn chờ, cho quản lý xác nhận một lệnh mới. |

## Tiêu chí nghiệm thu

| ID | Thiết lập và thao tác | Kết quả |
| --- | --- | --- |
| AC01 | Quản lý mở hàng đợi gồm nhiều trạng thái, có hai yêu cầu chờ cùng thời điểm gửi. Mở chi tiết một yêu cầu chờ. | Chỉ hiện yêu cầu chờ toàn CLB theo `created_at ASC, id ASC`, đủ trường nhận diện và giờ CLB. Chi tiết và hàng đợi nhất quán. |
| AC02 | Tải chậm, trả mảng rỗng, hoặc gây lỗi đọc rồi thử lại. | Hiện đủ trạng thái tải, rỗng, lỗi. Thử lại thành công đưa về dữ liệu mới. |
| AC03 | Hủy xác nhận, rồi duyệt một yêu cầu chờ có lịch trống. | Hủy giữ nguyên dữ liệu. Khi gửi, khóa nút đến khi có kết quả. 200, dòng rời hàng đợi, chi tiết thành viên là `APPROVED`, lịch mới chiếm khoảng và có đúng một sự kiện duyệt. |
| AC04 | Từ chối yêu cầu chờ đang trùng với lịch chiếm dụng. | 200, dòng rời hàng đợi, chi tiết thành viên là `REJECTED`, thêm đúng một sự kiện từ chối, lịch chiếm dụng giữ nguyên. |
| AC05 | Hai phiên quản lý gửi duyệt đồng thời qua hai kết nối SQL Server cho hai yêu cầu chờ cùng thiết bị, 09:00–10:00 và 09:30–10:30 cùng ngày. | Một 200 và một 409 `SCHEDULE_CONFLICT`. Một `APPROVED`, một `PENDING`, đúng một sự kiện. Hàng đợi sau tải lại giữ dòng bị xung đột và cho từ chối. |
| AC06 | Duyệt đồng thời hai yêu cầu cùng thiết bị, 09:00–10:00 và 10:00–11:00. Lặp lại với cùng 09:00–10:00 trên hai thiết bị. | Mỗi ca có hai 200 và hai sự kiện. Cả hai yêu cầu được duyệt. |
| AC07 | Hai phiên duyệt và từ chối đồng thời cùng một yêu cầu đủ điều kiện duyệt. Gửi lặp lệnh sau khi đã commit. | Chỉ một lần chuyển và một sự kiện. Các lệnh còn lại nhận 409 `INVALID_TRANSITION`. UI tải lại trạng thái và khóa thao tác với bản ghi đã xử lý. |
| AC08 | Gọi trực tiếp API với khách, thành viên có CSRF hợp lệ hoặc quản lý thiếu CSRF. Thử chi tiết thuộc người khác bằng tài khoản thành viên. | Lần lượt 401, 403 `FORBIDDEN`, 403 `CSRF_INVALID` và 404. Danh sách thành viên vẫn dùng phạm vi #113. |
| AC09 | Gây lỗi ghi sự kiện. Mô phỏng mất phản hồi sau commit và lỗi đọc lại chi tiết. | Lỗi ghi rollback cả cập nhật và sự kiện. Khi chưa rõ kết quả, UI đợi đọc lại thành công trước khi bật thao tác. Commit đã xảy ra được phản ánh qua chi tiết và hàng đợi, chỉ có một sự kiện. |
| AC10 | Duyệt lần lượt với khoảng giao nhau của các trạng thái `HANDED_OVER`, `PENDING`, `REJECTED`, `RETURNED` trên cùng thiết bị, mỗi ca dùng dữ liệu riêng. | `HANDED_OVER` gây xung đột. Các trạng thái còn lại cho phép duyệt nếu lịch trống. |

## Điểm FE và BE cần thống nhất

- Dùng `GET /loan-requests` và `GET /loan-requests/{id}` cho danh sách và chi tiết. FE và BE đối chiếu phản hồi quản lý gồm `id`, `equipment_id`, `borrower_id`, `start_at`, `end_at`, `created_at`, `status`, `equipment_asset_code`, `equipment_name`, `borrower_username`. Thời gian API là ISO 8601 UTC có hậu tố `Z`. FE giữ thứ tự từ API.
- Gửi `POST /loan-requests/{id}/approve` hoặc `/reject` với body rỗng, cookie phiên và `X-CSRF-Token`. POST 200 trả bản ghi của lần cập nhật đã commit. FE dùng GET chi tiết khi cần dữ liệu JOIN mới. Lỗi trả `{"code":"..."}` theo bảng ngoại lệ. FE ánh xạ code thành thông báo tiếng Việt.
- FE và BE thống nhất hành vi khi phản hồi đến muộn, khi làm mới chi tiết và khi hàng đợi đã đổi trong phiên quản lý khác. FE chỉ bỏ dòng khi có kết quả thành công hoặc dữ liệu mới xác nhận dòng đã rời hàng đợi.
- Khi tích hợp, BE đối chiếu migration thực tế của #112, dùng phiên và CSRF của #111, nối trạng thái thành viên qua #113 và phối hợp #115–116 về thứ tự khóa. QA dùng dữ liệu tổng hợp và kiểm chứng các ca đồng thời trên SQL Server, gồm HTTP, trạng thái lưu và số sự kiện.

## Mở prototype

Mở `story-114-prototype.html` trực tiếp trong trình duyệt. Chọn kịch bản và bấm “Nạp kịch bản”. Dữ liệu và phản hồi được mô phỏng trong trình duyệt. Kịch bản mẫu có hai yêu cầu trùng giờ, một yêu cầu sát biên và một yêu cầu cùng giờ trên thiết bị khác. Duyệt YC-101 rồi thử YC-102 để thấy xung đột. Có thể từ chối YC-102 từ hàng đợi sau khi thông báo xuất hiện. Các kịch bản riêng mô phỏng hàng đợi rỗng, lỗi tải, thay đổi từ phiên khác và mất phản hồi sau commit.
