# SRS · Xác nhận nhận lại thiết bị

Story #116 · Task BA #135 · Cơ sở: Redmine #116 và [thiết kế SA #134](story-116-sa-design.md)

## Luồng nghiệp vụ

1. Quản lý mở **Yêu cầu đã giao**. Danh sách chỉ lấy yêu cầu `HANDED_OVER`. Mỗi dòng có mã yêu cầu, thiết bị, người mượn, giờ đặt và nút **Xác nhận nhận lại**.
2. Hộp thoại nhắc lại mã yêu cầu và thiết bị. Quản lý chọn **Hủy** để quay về hoặc chọn **Xác nhận nhận lại** sau khi đã nhận thiết bị. Trong lúc gửi, hiển thị tiến trình và khóa thao tác gửi lại.
3. Khi giao dịch thành công, hiển thị **Đã trả** cùng người nhận và giờ nhận cho quản lý, rồi tải lại danh sách đã giao. Nếu tải danh sách lỗi sau đó, giữ thông báo thành công và cho thử tải lại.
4. Khi thành viên tải lại danh sách hoặc chi tiết yêu cầu của mình, hiển thị **Đã trả** và giữ khoảng đặt gốc để tra cứu. Quản lý có thể xem lại thông tin nhận trong chi tiết.
5. Tra cứu lịch mới sau commit bỏ khoảng đặt của lượt đã trả. Lượt đã duyệt kế tiếp vẫn giữ chỗ và đi qua luồng xác nhận giao của #115.

## Tiêu chí nghiệm thu

| Mã | Điều kiện và kết quả quan sát được |
|---|---|
| AC1 | Với phiên quản lý hợp lệ và yêu cầu đang **Đã giao**, xác nhận tạo đúng một sự kiện `HANDED_OVER → RETURNED`. Danh tính lấy từ phiên, thời điểm do SQL Server cấp theo UTC. Chi tiết quản lý hiển thị người nhận và thời điểm theo giờ CLB. Yêu cầu rời danh sách đã giao sau khi tải lại. |
| AC2 | Thành viên sở hữu yêu cầu tải lại danh sách hoặc chi tiết và thấy **Đã trả** cùng giờ đặt gốc. Thành viên khác đọc chi tiết nhận `404`. |
| AC3 | A đặt 09:00–11:00, nhận lúc 10:00. B cùng thiết bị đã duyệt 11:00–12:00. Tra cứu mới từ 10:00–12:00 sau commit cho thấy 10:00–11:00 trống và 11:00–12:00 bận. Khi còn các khoảng đặt hợp lệ khác, lịch giữ nguyên các khoảng đó. Hai khoảng tiếp giáp tại một đầu mút được xử lý theo quy ước khoảng nửa mở. |
| AC4 | Khi A còn **Đã giao**, kể cả quá giờ đặt, xác nhận giao B trả `409 EQUIPMENT_IN_USE` và B vẫn **Đã duyệt**. Sau khi nhận A, xác nhận giao B thành công nếu thỏa các điều kiện #115. |
| AC5 | Hủy hộp thoại giữ nguyên trạng thái và trả tiêu điểm về nút mở. Khi tải danh sách hoặc chi tiết, thông báo đang tải. Danh sách đã giao rỗng có thông báo riêng. Lỗi tải có nút thử lại. Trong lúc gửi, thao tác xác nhận chỉ phát một lệnh. |
| AC6 | Hai quản lý xác nhận cùng yêu cầu tạo đúng một sự kiện. Lệnh thắng trả `200`, lệnh còn lại trả `409 INVALID_TRANSITION`. Tải lại hiển thị người và giờ của sự kiện đã lưu. |
| AC7 | Mô phỏng lỗi ghi sự kiện trước commit. Trạng thái, nhật ký và kết quả tra cứu vẫn phản ánh lượt đang giao. Mô phỏng mất phản hồi sau commit. Tải lại chi tiết cho thấy đã trả và giao diện hiển thị kết quả đã lưu. |
| AC8 | Kiểm thử đồng thời giao B và nhận A trên hai kết nối SQL Server. Khi giao lấy khóa trước, B nhận `EQUIPMENT_IN_USE`. Khi nhận commit trước, giao đọc trạng thái mới dưới khóa và thành công nếu thỏa #115. |
| AC9 | Khi lần đọc chi tiết sau lỗi ghi hoặc mất phản hồi cũng thất bại, giao diện báo chưa xác định được kết quả và có nút **Thử tải lại chi tiết**. Chỉ hiện lại thao tác xác nhận nếu lần đọc thành công cho thấy yêu cầu còn **Đã giao**. |

## Ngoại lệ và phục hồi

| Tình huống | Hành vi |
|---|---|
| Phiên thiếu hoặc hết hạn (`401`) | Yêu cầu đăng nhập lại, sau đó tải dữ liệu hiện hành. |
| Vai trò thiếu quyền hoặc CSRF sai (`403`) | Báo thiếu quyền hoặc phiên biểu mẫu hết hiệu lực theo mã lỗi. Với `CSRF_INVALID`, tải lại để lấy token mới theo cơ chế #111. |
| ID sai định dạng (`400`), ID không tồn tại (`404`) | Thông báo yêu cầu không hợp lệ hoặc không còn tồn tại. Cho quay lại danh sách. |
| Sai trạng thái (`409 INVALID_TRANSITION`) | Tải lại chi tiết. Nếu đã trả, hiển thị kết quả đã lưu. Với trạng thái khác, cập nhật giao diện theo máy chủ và ẩn thao tác nhận lại nếu không đủ điều kiện. |
| Mạng gián đoạn, mất phản hồi hoặc lỗi máy chủ | Giữ thông báo chưa xác định được kết quả và tải lại chi tiết trước khi cho xác nhận lại. Nếu đọc được **Đã trả**, hiển thị kết quả đã lưu. Nếu vẫn **Đã giao**, cho xác nhận lại. Nếu đọc thất bại, cho thử tải chi tiết. |

## Bàn giao FE và BE

- Dùng phiên cùng origin, vai trò quản lý và `X-CSRF-Token` theo #111. Lệnh đề xuất `POST /loan-requests/{id}/return` có body rỗng. Phản hồi `200` sau commit dùng DTO hiện hành, với `status: RETURNED`, `returned_by` kiểu ID và `returned_at` ISO 8601 UTC dành cho quản lý. FE và BE cần thống nhất nguồn nhãn người nhận, cấu trúc lỗi và quy ước tiền tố API.
- Đối chiếu bộ lọc `GET /loan-requests?status=HANDED_OVER`, DTO chi tiết và phạm vi sở hữu với #113–115. Khi nhận thành công, làm mới danh sách quản lý. Khi mở lại hoặc tải lại, chi tiết thành viên và lịch dùng dữ liệu mới. Hiển thị thời điểm theo `Asia/Bangkok`.
- BE dùng Microsoft SQL Server và T-SQL. Ghi trạng thái và sự kiện cùng giao dịch, khóa thiết bị trước khi khóa yêu cầu như #114–115. Giờ nhận lấy từ `SYSUTCDATETIME()`. Lịch #112 lấy hợp các khoảng `APPROVED` và `HANDED_OVER` trong cửa sổ truy vấn. Cần đối chiếu schema, migration và API thực tế của #112–115 trước khi tích hợp và chạy các ca SQL Server.
- [Prototype HTML](story-116-prototype.html) mở trực tiếp, dùng dữ liệu giả lập và giờ minh họa cố định. Dùng mục **Kịch bản mô phỏng** để thử trạng thái tải, rỗng, lỗi và phục hồi. Màn lịch minh họa cửa sổ 10:00–12:00. Nút giao kế tiếp minh họa quy tắc thiết bị đang rảnh của #115.
- Prototype đặt liên kết **Xem chi tiết MT-024** ở màn quản lý sau khi nhận lại để minh họa tra cứu nhật ký. Khi tích hợp, dùng điểm vào chi tiết quản lý hiện hành của #114–115. Màn thành viên có danh sách, chi tiết và thao tác tải lại chi tiết.
