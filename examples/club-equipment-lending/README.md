# Club Equipment Lending

## Cài và kiểm tra từ thư mục gốc

Cần Node.js 26 trở lên, npm, Microsoft SQL Server và Caddy để mở giao diện qua HTTPS.

Trên Windows, nếu có nhiều bản cài Node.js, chạy `Get-Command node,npm -All` và đặt thư mục cài Node.js 26 cùng npm đi kèm lên đầu `PATH` của terminal trước khi cài và kiểm thử.

```powershell
npm ci
npm test
npm run build
```

`npm test` kiểm tra API HTTP bằng dữ liệu tổng hợp, gồm đăng ký thành viên, phiên, phân quyền, tra cứu lịch, gửi và theo dõi yêu cầu mượn, hàng đợi quản lý, duyệt, từ chối, xác nhận giao và xác nhận nhận lại. Lệnh này cũng chạy kiểm thử frontend về quản lý phiên và xác nhận nhận lại với API mô phỏng. `npm run build` kiểm tra cú pháp JavaScript của ứng dụng và chép giao diện vào `dist/`. Workflow `lending-validation` chạy ba lệnh trên cho pull request với Node.js 26.

## Chạy bản demo

1. Tạo database SQL Server riêng `ClubEquipmentLending_Preview` và cấp cho tài khoản demo quyền chạy migration và thao tác trên database này. Đặt `DATABASE_URL` bằng chuỗi kết nối SQL Server dành cho demo. Nếu dùng shared memory trên Windows, đặt thêm `SQLSERVER_DRIVER=odbc` và dùng chuỗi ODBC. Xem [hướng dẫn backend](backend/README.md).
2. Trong PowerShell đã cấu hình kết nối, chạy các lệnh sau. Thay hai giá trị mật khẩu bằng mật khẩu tổng hợp do bạn chọn. Seed giữ nguyên mật khẩu của tài khoản đã tồn tại.

   ```powershell
   $env:LENDING_ENV = 'demo'
   $env:DEMO_MEMBER_PASSWORD = 'synthetic-member-demo'
   $env:DEMO_MANAGER_PASSWORD = 'synthetic-manager-demo'
   npm run migrate
   npm run seed
   $env:APP_ORIGIN = 'https://localhost:8443'
   $env:HOST = '127.0.0.1'
   $env:PORT = '3000'
   npm start
   ```

3. Từ thư mục gốc, mở terminal khác và chạy `caddy run --config Caddyfile`. Cấu hình phục vụ `dist/` và chuyển tiếp API về cổng 3000 trên cùng origin. Nếu trình duyệt chưa tin cậy CA nội bộ của Caddy, chạy `caddy trust` với quyền phù hợp rồi mở `https://localhost:8443/`.
4. Mở trực tiếp `/#equipment` và `/#management` khi chưa đăng nhập. Đăng nhập lần lượt bằng `demo.member` và `demo.manager`, kiểm tra hai mã thiết bị `DEMO-01` và `DEMO-02`, tải lại trang rồi đăng xuất. Thành viên thấy thông báo thiếu quyền tại màn Quản lý. Xem [kịch bản kiểm tra giao diện](frontend/README.md).
5. Với database demo mới chạy migration và seed, mở **Xem lịch** cho `DEMO-01`, nhập ngày 16/11/2026 từ 09:00 đến 13:00 và tra cứu. Kiểm tra giao diện hiển thị toàn bộ khoảng 09:00–13:00 theo Asia/Bangkok (UTC+07:00). Trong tab Network, kiểm tra yêu cầu `/equipment/{id}/availability` qua `https://localhost:8443` trả JSON `200` và chỉ có thông tin thiết bị, múi giờ và các mốc thời gian. Lặp lại với `DEMO-02` và tài khoản quản lý. Các ca có lịch bận dùng fixture tổng hợp trong [hướng dẫn frontend](frontend/README.md#kiểm-tra-lịch-trống-story-112).

6. Với `demo.member`, mở **Yêu cầu của tôi** và thực hiện [kịch bản Story #113](frontend/README.md#chạy-thử-story-113). Kiểm tra giờ bắt đầu phải trước giờ kết thúc, hai lượt gửi trùng giờ đều **Chờ duyệt** và chi tiết sau khi tải lại. Ca truy cập bằng thành viên thứ hai cần tài khoản thành viên tổng hợp bổ sung. Bộ kiểm thử SQL Server tạo sẵn tài khoản này trong schema kiểm thử.
7. Thực hiện [kịch bản Story #114](frontend/README.md#chạy-thử-story-114) sau khi migration đã áp dụng `004-loan-events.sql`. Dùng hai cửa sổ có phiên độc lập để kiểm tra đồng thời. Xác nhận yêu cầu trùng giờ bị xung đột vẫn nằm trong hàng đợi và có thể được từ chối. Duyệt tiếp yêu cầu sát biên trên cùng thiết bị và yêu cầu cùng giờ trên thiết bị khác.
8. Thực hiện [kịch bản Story #115](frontend/README.md#chạy-thử-story-115) sau khi migration đã áp dụng `005-loan-request-active-holder.sql`. Duyệt hai yêu cầu sát biên cho cùng thiết bị, rồi giao lượt đầu từ **Yêu cầu đã duyệt**. Khi thử giao lượt kế tiếp, kiểm tra phản hồi `409 EQUIPMENT_IN_USE` trong tab Network và xác nhận lượt này vẫn **Đã duyệt**. Tải lại danh sách và chi tiết trong phiên thành viên để thấy lượt đầu **Đã giao**.

9. Tiếp tục với hai lượt ở bước 8 theo [kịch bản Story #116](frontend/README.md#chạy-thử-story-116). Trong phiên quản lý, mở **Yêu cầu đã giao**, xác nhận nhận lại lượt đầu và mở chi tiết để kiểm tra **Đã trả**, người nhận và thời điểm nhận theo giờ CLB. Trong phiên thành viên, tải lại yêu cầu để kiểm tra **Đã trả** cùng giờ đặt gốc. Tra lịch qua cả hai khoảng đặt để kiểm tra khoảng đầu đã trống và lượt kế tiếp vẫn giữ chỗ, rồi giao lượt kế tiếp từ phiên quản lý. Migration hiện có đã hỗ trợ quy trình nhận lại.

## Kiểm thử với SQL Server

Với Story #176, chạy theo [kịch bản đăng ký](frontend/README.md#chạy-thử-story-176) sau khi khởi động demo. Dùng tên đăng nhập tổng hợp mới và nhập `abcdef😀` để thấy lỗi 7 điểm mã. Trên cùng biểu mẫu, đổi thành `abcdefg😀`, tạo tài khoản rồi quay về màn đăng nhập, đăng nhập thủ công và mở danh mục thiết bị. Dùng tài khoản `demo.member` đã có để kiểm tra lại đăng nhập bằng mật khẩu cũ.

Với Story #166, mở [kịch bản đăng ký trên giao diện](frontend/README.md#chạy-thử-story-166) sau khi khởi động demo. Dùng tên đăng nhập tổng hợp chưa có trong database, đăng nhập thủ công sau khi tạo tài khoản và kiểm tra danh mục. Bộ kiểm thử SQL Server kiểm tra thêm trường vai trò gửi trực tiếp, đăng ký đồng thời với tên trùng, băm Argon2id và phản hồi `403` khi tài khoản mới gọi API quản lý.

Đặt `TEST_DATABASE_URL` trỏ tới database riêng `ClubEquipmentLending_Test` với quyền tạo và xóa schema thử nghiệm. Nếu dùng ODBC, đặt `SQLSERVER_DRIVER=odbc`. Chạy `npm run test:sqlserver` từ thư mục gốc để kiểm tra migration, seed lặp lại, hai ID thiết bị, vòng đời phiên và lịch trống với dữ liệu tổng hợp cho từng trạng thái yêu cầu. Bài kiểm thử cũng gửi đồng thời hai yêu cầu trùng giờ, xác nhận cả hai được lưu với mã riêng ở trạng thái `PENDING` và kiểm tra truy cập từ thành viên khác. Bộ kiểm thử tự tạo và dọn fixture trong schema riêng. Dùng dữ liệu tổng hợp cho cả database demo và test.

## Xác minh SQL Server trên máy điều hành

- Story #176 đạt 3/3 theo log `1795032442695776100-story-176-sqlserver.log`. Bài API xác nhận mật khẩu 7 điểm mã trả `400 INVALID_INPUT` và không tạo tài khoản. Mật khẩu 8 điểm mã có emoji tạo được tài khoản `MEMBER` với băm Argon2id. Log `1795032439425704600-story-176-browser/browser.log` và ba ảnh cùng thư mục ghi nhận lỗi 7 điểm mã, xác nhận tạo tài khoản sau khi sửa thành 8 điểm mã và danh mục sau khi đăng nhập thủ công. Bộ điều phối chạy trình duyệt với API thật và schema SQL Server kiểm thử riêng dùng dữ liệu tổng hợp.
- Story #166 đạt 3/3 trên checkout tích hợp theo log `1794989572054110400-story-166-sqlserver.log` của bộ điều phối. Hai lượt đăng ký đồng thời cho cùng tên nhận một `201` và một `409`. Tài khoản được lưu với vai trò `MEMBER` và mật khẩu băm Argon2id, đăng nhập được và nhận `403` khi gọi API quản lý.
- Story #116 đạt 2/2 theo log `1794934432913076600-story-116-sqlserver.log` của bộ điều phối. Các ca kiểm tra gồm xác nhận nhận lại đồng thời, hoàn tác khi ghi sự kiện lỗi, người nhận và thời điểm nhận, trạng thái thành viên, giải phóng lịch và giao lượt kế tiếp.
- Story #115 đạt 2/2 theo log `1794917357493976400-story-115-sqlserver.log` của bộ điều phối. Bộ kiểm thử xác nhận giao đồng thời trên cùng thiết bị, trạng thái của lượt bị chặn và lượt đã giao khi thành viên đọc lại, người giao và thời điểm giao, cùng việc hoàn tác khi không ghi được sự kiện.
- Story #114 đạt 2/2 trên cùng checkout theo log `1794915959443558300-story-114-sqlserver.log` của bộ điều phối. Bài kiểm thử qua HTTP xác nhận đúng một lượt duyệt thành công khi chồng giờ trên cùng thiết bị, lượt còn lại nhận `409 SCHEDULE_CONFLICT` và giữ `PENDING`. Các ca sát biên, khác thiết bị và hoàn tác khi ghi sự kiện lỗi đều đạt.
- Story #112 đạt 1/1 trên cùng checkout theo log `1794747700991673500-story-112-sqlserver.log` của bộ điều phối.
- Xem [kết quả kiểm thử tích hợp Story #111](story-111-sqlserver-verification.md).
