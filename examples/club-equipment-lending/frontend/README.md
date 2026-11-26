# Chạy thử giao diện mượn thiết bị

1. Dùng cơ sở dữ liệu SQL Server dành cho demo/test. Chạy migration và seed theo [hướng dẫn backend](../backend/README.md), đặt hai mật khẩu tổng hợp qua `DEMO_MEMBER_PASSWORD` và `DEMO_MANAGER_PASSWORD`.
2. Khởi động API với `APP_ORIGIN=https://localhost:8443` và cổng mặc định `3000`.
3. Từ thư mục gốc dự án chạy `npm run build`, sau đó chạy `caddy run --config Caddyfile`. Caddy phục vụ bản build trong `dist` và chuyển tiếp các API phiên, danh mục, lịch và yêu cầu mượn trên cùng origin HTTPS. [Caddyfile](../Caddyfile)

   Dùng chứng chỉ mà trình duyệt tin cậy. Với Caddy cục bộ, có thể dùng `caddy trust` để cài CA nội bộ khi tài khoản có quyền. Truy cập `https://localhost:8443/`.

## Chạy thử Story #176

1. Dùng môi trường HTTPS và dữ liệu SQL Server tổng hợp theo hướng dẫn trên. Từ **Đăng nhập**, chọn **Đăng ký** và nhập tên mới, ví dụ `demo.member176` (thêm hậu tố khi chạy lại).
2. Gửi với `abc123😀` (7 điểm mã). Kiểm tra lỗi **Mật khẩu phải có ít nhất 8 ký tự** cạnh trường mật khẩu. Sửa thành `abc1234😀` (8 điểm mã) và gửi lại. Kiểm tra xác nhận **Đã tạo tài khoản**.
3. Chọn **Về đăng nhập**. Kiểm tra tên đã điền và ô mật khẩu trống. Tự nhập mật khẩu vừa tạo, đăng nhập rồi mở **Danh mục thiết bị** để xem thiết bị demo.

### Kiểm tra Task #180

- `npm test` đạt 17/17 ca. Ca frontend dùng DOM và API mô phỏng để kiểm tra biên 7/8 điểm mã với emoji, Unicode không hợp lệ, giới hạn byte và luồng đăng nhập thủ công vào danh mục.
- `npm run build` và `git diff --check` đạt. Bài SQL Server của bộ điều phối đạt 3/3 theo log `1795032354730358100-story-176-sqlserver.log`. Bài kiểm tra đăng ký xác nhận API từ chối 7 điểm mã và không tạo tài khoản, chấp nhận 8 điểm mã có emoji, lưu băm Argon2id, xử lý đăng ký trùng đồng thời và kiểm tra quyền thành viên.
- Log `1795032351431363100-story-176-browser/browser.log` xác nhận trình duyệt chạy với API thật và schema SQL Server riêng dùng dữ liệu tổng hợp. Bài chạy ghi nhận lỗi ở 7 điểm mã rồi sửa thành đúng 8 điểm mã có emoji trên cùng biểu mẫu. Tài khoản thành viên được tạo, phản hồi đăng ký không cấp cookie phiên và người dùng đăng nhập thủ công để mở danh mục.
- Cùng thư mục log trình duyệt có ba ảnh `short-password-error.png`, `registered.png` và `catalog.png`. Bài chạy cũng kiểm tra biểu mẫu trống, tên trùng và thử lại sau lỗi mạng.

## Chạy thử Story #166

1. Mở ứng dụng demo HTTPS khi chưa đăng nhập. Từ **Đăng nhập**, chọn **Đăng ký**. Gửi biểu mẫu trống, sau đó thử tên có dấu cách ở giữa hoặc mật khẩu ngắn. Kiểm tra lỗi cạnh trường và tiêu điểm ở trường lỗi đầu tiên.
2. Đăng ký bằng tên tổng hợp chưa dùng, ví dụ `  DEMO.Member166  `, và mật khẩu tổng hợp đạt các quy tắc hiển thị. Kiểm tra trạng thái **Đang tạo tài khoản…** trong lúc gửi, sau đó kiểm tra **Đã tạo tài khoản** với tên `demo.member166`.
3. Chọn **Về đăng nhập**. Kiểm tra tên đã điền và ô mật khẩu trống. Tự nhập mật khẩu để đăng nhập, kiểm tra danh mục tải và điều hướng chỉ hiển thị chức năng của thành viên.
4. Đăng xuất rồi đăng ký lại cùng tên. Kiểm tra thông báo tên đã được sử dụng cạnh ô tên và sửa tên để thử lại. Dùng hồ sơ trình duyệt khác nếu cần kiểm tra hai lượt gửi đồng thời.
5. Trong môi trường demo, mô phỏng mất phản hồi để kiểm tra hướng dẫn đăng nhập hoặc gửi lại. Mô phỏng phản hồi 429 có `Retry-After` để kiểm tra đếm ngược và mở lại nút gửi.

### Kiểm tra Task #170

- `npm test` đạt 16/16 ca, gồm 4 ca HTTP backend và 12 ca frontend hiện có. `npm run build` và `git diff --check` đều đạt.
- Chrome headless chạy bản build với phản hồi API mô phỏng. Đã kiểm tra xác thực trường và tiêu điểm, khóa gửi lặp, phản hồi 201/400/403/409/429/500, mất mạng, xóa mật khẩu, đăng nhập thủ công, điều hướng theo vai trò và danh mục đang tải, có dữ liệu, lỗi, rỗng và hết phiên.
- Bộ điều phối chạy bộ kiểm thử SQL Server trên checkout của Story #166 và báo đạt 3/3 theo log `1794988870540073400-story-166-sqlserver.log`. Ca đăng ký đồng thời xác nhận chỉ tạo một tài khoản thành viên và chặn API quản lý đối với tài khoản đó.

## Chạy thử Story #116

1. Dùng môi trường demo theo hướng dẫn trên. Tạo hai lượt sát biên cho cùng thiết bị, duyệt cả hai, rồi giao lượt đầu. Thử giao lượt kế tiếp và kiểm tra cảnh báo thiết bị còn được giữ.
2. Mở **Yêu cầu đã giao** (`/#management/handed-over`), bấm **Xác nhận nhận lại**, rồi chọn **Hủy** để kiểm tra tiêu điểm quay về nút mở. Mở lại và xác nhận. Kiểm tra lượt đã trả rời danh sách và chọn **Xem chi tiết** để xem **Đã trả**, người nhận và giờ CLB.
3. Trong phiên thành viên, tải lại **Yêu cầu của tôi** và mở chi tiết. Kiểm tra **Đã trả** cùng giờ đặt gốc. Tra lịch cho khoảng đặt của cả hai lượt để thấy lượt đã trả được giải phóng và lượt đã duyệt vẫn giữ chỗ. Quay về phiên quản lý để giao lượt kế tiếp.

Để kiểm tra bug #165, ghi lại mã YC của yêu cầu trên thẻ trước khi xác nhận. Sau khi xác nhận nhận lại, tải lại trang **Yêu cầu đã giao** trước khi mở liên kết trong thông báo. Nhập mã YC vào ô **Mã yêu cầu** và bấm **Tra cứu chi tiết**. Kiểm tra trạng thái **Đã trả**, người nhận và giờ nhận theo giờ CLB. Quản lý cũng có thể dán mã từ phiên trước. Tra cứu dùng API chi tiết, theo mã hiển thị trên thẻ.
4. Mô phỏng mất phản hồi của lệnh nhận và chặn lần đọc chi tiết kế tiếp. Kiểm tra thao tác nhận vẫn bị khóa và có nút **Thử tải lại chi tiết**. Bỏ chặn và thử lại để xem kết quả đã lưu hoặc mở lại thao tác nếu lượt vẫn **Đã giao**. Nếu lệnh thành công nhưng tải danh sách lỗi, kiểm tra thông tin nhận vẫn hiện khi thử tải danh sách lại.
5. Dùng phiên thành viên mở trực tiếp đường dẫn quản lý để kiểm tra thông báo thiếu quyền. Dùng phiên quản lý hết hạn để kiểm tra quy trình đăng nhập lại và tải trạng thái hiện hành.

### Kiểm tra Task #157

- `npm test` đạt 3/3 ca HTTP backend và 11/11 ca FE với DOM, mạng mô phỏng. Bộ FE kiểm tra hủy, khóa gửi lặp, CSRF, biên nhận theo giờ CLB, lỗi tải danh sách, xung đột, mất phản hồi, thử tải lại và chặn thành viên.
- Chrome headless chạy bản build với API mô phỏng và dữ liệu tổng hợp. Đã xác minh tiêu điểm sau khi hủy, xác nhận nhận lại, tra cứu biên nhận và trạng thái **Đã trả** kèm giờ đặt gốc ở danh sách và chi tiết thành viên.
- `npm run build` và `git diff --check` đều đạt.
- Bộ điều phối đã chạy SQL Server trên checkout của Story #116, đạt 2/2 theo log `1794934031377062500-story-116-sqlserver.log`.

## Chạy thử Story #115

1. Thiết lập môi trường demo như trên, áp dụng thêm migration `005-loan-request-active-holder.sql`. Dùng `demo.member` tạo hai yêu cầu sát biên cho cùng thiết bị. Dùng `demo.manager` duyệt cả hai.
2. Mở **Yêu cầu đã duyệt** (`/#management/approved`), vào chi tiết lượt đầu và chọn **Xác nhận giao**. Kiểm tra chi tiết hiện **Đã giao** và lượt đầu rời danh sách đã duyệt khi quay về.
3. Thử giao lượt kế tiếp. Chi tiết báo thiết bị vẫn đang được giữ và lượt này vẫn **Đã duyệt**. Tải lại **Yêu cầu của tôi** trong phiên thành viên và mở chi tiết lượt đầu để thấy **Đã giao** ở cả hai màn hình.
4. Mô phỏng mất phản hồi POST. Kiểm tra nút giao bị khóa. Chọn **Tải lại chi tiết**. Nếu đã lưu, chi tiết hiện **Đã giao**. Nếu vẫn **Đã duyệt**, có thể thử giao lại. Chặn lượt đọc trạng thái để kiểm tra giao diện vẫn khóa nút giao và cho thử tải lại.
5. Dùng phiên thành viên mở trực tiếp danh sách đã duyệt hoặc chi tiết quản lý. Kiểm tra màn hình báo thiếu quyền. Với phiên quản lý hết hạn, đăng nhập lại và kiểm tra chi tiết được tải trước khi có thể giao.

### Kết quả Task #146

- Chrome headless kiểm tra bản build cục bộ với phản hồi API mô phỏng và dữ liệu tổng hợp. Đạt các ca danh sách lọc, tải và lỗi đọc, rỗng, khóa gửi lặp, giao thành công, thiết bị còn được giữ, đổi trạng thái, làm mới CSRF, thiếu quyền, hết phiên, mất phản hồi trước và sau khi lưu, đọc lại thất bại và hai màn hình thành viên.
- `npm run build`, `npm test` (3/3), `node --test frontend/test/management-session.test.cjs` (5/5) và `git diff --check` đều đạt. Bộ điều phối chạy kiểm thử SQL Server trên cùng checkout và báo đạt 2/2 theo log `1794917045755727900-story-115-sqlserver.log`. Kiểm thử trình duyệt dùng phản hồi mô phỏng. Chạy thử tích hợp qua HTTPS với SQL Server theo các bước trên.

## Chạy thử Story #114

1. Dùng môi trường demo theo hướng dẫn trên, áp dụng cả migration `004-loan-events.sql`. Với `demo.member`, tạo hai yêu cầu chồng giờ trên DEMO-01, một yêu cầu bắt đầu đúng lúc yêu cầu đầu kết thúc và một yêu cầu cùng giờ yêu cầu đầu trên DEMO-02.
2. Với `demo.manager`, mở **Quản lý** (`/#management`). Kiểm tra thứ tự gửi cũ trước, mã yêu cầu, thiết bị, người gửi và giờ CLB. Mở **Chi tiết**, chọn **Duyệt** rồi **Hủy** để kiểm tra yêu cầu vẫn chờ. Xác nhận duyệt và kiểm tra chi tiết đổi thành **Đã duyệt**, hàng đợi bỏ dòng tương ứng.
3. Để thử đồng thời, tạo lại bốn yêu cầu ở một ngày khác. Mở hàng đợi trong hai phiên quản lý và xác nhận duyệt hai yêu cầu chồng giờ trước khi một phiên nhận phản hồi. Kiểm tra một yêu cầu được duyệt, yêu cầu kia vẫn chờ và có cảnh báo xung đột. Từ chối yêu cầu còn chờ rồi duyệt hai yêu cầu sát biên và khác thiết bị.
4. Chặn GET danh sách hoặc chi tiết trong công cụ mạng rồi bỏ chặn và bấm **Thử lại**. Khi POST bị lỗi sau lúc gửi, kiểm tra hai nút quyết định bị khóa trong lúc đối chiếu. Nếu lượt đọc lại lỗi, bỏ chặn và chọn **Tải lại trạng thái**. Kiểm tra trạng thái đã lưu trước khi xác nhận lệnh tiếp theo.
5. Với tài khoản thành viên, mở thẳng `/#management` và `/#management/<id>` để kiểm tra thông báo thiếu quyền. Với phiên hết hạn, làm mới hàng đợi để kiểm tra ứng dụng đưa về màn hình đăng nhập.

### Kết quả Task #144

- Chạy `node --test frontend/test/management-session.test.cjs` từ thư mục gốc để kiểm tra hồi quy lỗi #162. Bài kiểm thử dùng API mô phỏng để điều khiển thứ tự phản hồi của POST và `/auth/me`.

- Chrome headless chạy bản build qua HTTP loopback với API mô phỏng và dữ liệu tổng hợp. Đạt các ca tải, rỗng, lỗi đọc và thử lại, hiển thị qua ngày ở màn hình 360 px với múi giờ trình duyệt America/Los_Angeles, mở chi tiết, hủy xác nhận, khóa nút khi gửi, duyệt, từ chối, xung đột, đổi trạng thái ở phiên khác, mất phản hồi sau lưu kèm lỗi đọc lại, làm mới CSRF, hết phiên và chặn thành viên.
- `npm run build`, `npm test` (3/3) và `git diff --check` đạt. Kết quả SQL Server do bộ điều phối cung cấp đạt 2/2 theo log `1794915430857494700-story-114-sqlserver.log`, gồm duyệt chồng giờ đồng thời, sát biên, khác thiết bị và hoàn tác khi ghi sự kiện lỗi. Môi trường này chưa có Caddy trên PATH nên lượt Chrome dùng HTTP loopback.

## Chạy thử Story #113

1. Đăng nhập bằng `demo.member`. Mở **Yêu cầu của tôi** (`/#requests`) rồi chọn **Gửi yêu cầu** (`/#request/new`). Cũng có thể chọn **Gửi yêu cầu** ngay dưới một khung giờ trống. Liên kết từ lịch dùng các tham số `equipment_id`, `start_at`, `end_at` với hai mốc UTC từ API lịch. Biểu mẫu hiển thị và cho chỉnh lại theo giờ CLB (UTC+7).
2. Chọn thiết bị mẫu, đặt giờ bắt đầu 09:00 và giờ kết thúc 09:00 cùng ngày. Kiểm tra lỗi cạnh ô kết thúc. Đổi giờ kết thúc thành 10:00 rồi gửi. Kiểm tra chi tiết hiện thông báo **Đã gửi yêu cầu** và nhãn **Chờ duyệt**. Gửi lại cùng thiết bị và khoảng giờ, rồi kiểm tra danh sách có hai mã riêng cùng chờ duyệt.
3. Mở một chi tiết từ danh sách rồi tải lại để đọc trạng thái hiện tại. Dùng phiên của một thành viên demo khác mở thẳng mã đó và một mã hợp lệ chưa tồn tại. Cả hai cùng hiện **Không tìm thấy yêu cầu**. Với `demo.manager`, mở thẳng `/#requests` hoặc `/#request/new` để thấy thông báo thiếu quyền.
4. Chặn lượt đọc `GET /loan-requests` hoặc `GET /loan-requests/{id}` trong công cụ mạng rồi thử lại sau khi bỏ chặn. Nếu lượt gửi trả lỗi máy chủ hoặc mất phản hồi, kiểm tra dữ liệu vẫn còn trên biểu mẫu và có thể về danh sách để đối chiếu kết quả.

### Kết quả Task #145

- Chrome headless qua loopback đã chạy giao diện với API backend và dữ liệu tổng hợp trong bộ nhớ. Kịch bản đạt các bước kiểm tra tải, rỗng, thử lại, điền từ lịch và quy đổi UTC với múi giờ trình duyệt America/Los_Angeles, chặn giờ bằng nhau, khóa biểu mẫu khi gửi, hai lượt trùng giờ, tải lại năm trạng thái, quyền sở hữu, hết phiên, thiếu quyền, CSRF sai, thiết bị mất và lỗi máy chủ sau khi ghi.
- `npm run build`, `npm test` (3/3) và `git diff --check` đạt.
- Dùng kết quả SQL Server do bộ điều phối cung cấp, đạt 1/1 theo log `1794913709051626400-story-113-sqlserver.log`. Lượt Chrome chạy trực tiếp với API qua loopback. Có thể chạy thử bản HTTPS qua Caddy theo các bước ở đầu tài liệu.

## Kiểm tra phiên và danh mục

- Mở trực tiếp `/#equipment` và `/#management` trong cửa sổ riêng tư. Cả hai đưa khách về đăng nhập.
- Dùng nút điền tên `demo.member` rồi nhập mật khẩu đã seed. Thử mật khẩu sai trước. Đăng nhập đúng sẽ hiển thị hai máy chiếu với mã `DEMO-01` và `DEMO-02`. Mở `/#management` để kiểm tra thông báo thiếu quyền và liên kết về danh mục.
- Đăng xuất và đăng nhập bằng `demo.manager`. Mục Quản lý xuất hiện. Mở mục này và tải lại trang để kiểm tra phiên. Đăng xuất rồi mở lại liên kết quản lý để kiểm tra việc chặn truy cập.
- Dùng công cụ mạng của trình duyệt để chặn riêng `GET /equipment` trong lúc điều hướng từ màn Quản lý sang Danh mục. Bỏ chặn rồi bấm **Thử lại**. Phản hồi `200` với `[]` hiển thị trạng thái danh mục trống. Phản hồi `401` khi đang đăng nhập đưa người dùng về màn đăng nhập với thông báo hết phiên.
- Chạy `npm test` trong `backend` để kiểm tra thành viên gọi trực tiếp handler quản lý nhận `403`. Chạy `npm run test:sqlserver` theo README backend để kiểm tra seed, hai ID vật lý và vòng đời phiên trên SQL Server.

## Kiểm tra lịch trống Story #112

1. Đăng nhập bằng tài khoản demo và bấm **Xem lịch** ở DEMO-01. Kiểm tra thiết bị chọn sẵn theo mã tài sản và nhãn **Asia/Bangkok (UTC+07:00)** ở cả bộ nhập và kết quả. Hai trường giờ bắt đầu trống.
2. Với fixture tổng hợp AC1 trong [SRS](../story-112-srs.md), tra ngày 16/11/2026 từ 09:00 đến 13:00. Kết quả DEMO-01 là 11:00–13:00. Đổi sang DEMO-02 và tra lại để thấy 09:00–13:00. DEMO-01 từ 09:00 đến 11:00 báo không có giờ trống. Tra lại bằng tài khoản quản lý để kiểm tra quyền.
3. Đổi múi giờ trình duyệt sang America/Los_Angeles và kiểm tra mốc gửi tương ứng 02:00Z và 06:00Z. Tra qua đêm và kiểm tra ngày ở cả hai mốc. Bỏ trống, nhập trùng hoặc đảo mốc để kiểm tra lỗi cạnh trường, tiêu điểm và việc không gửi yêu cầu.
4. Làm chậm phản hồi lịch rồi đổi đầu vào và tra lượt mới. Kết quả chỉ phản ánh lượt mới. Chặn API lịch rồi bỏ chặn để thử nút **Thử lại**. Với 401, màn đăng nhập xuất hiện và lịch được xóa. Với 403, màn hình báo thiếu quyền. Với 404, **Tải lại danh mục** mở danh mục và tải các thiết bị hiện có.
5. Với fixture đầy đủ trong SRS, tra DEMO-01 từ 06:00 đến 15:00. Kiểm tra ba khoảng theo thứ tự 06:00–07:00, 11:00–13:00 và 14:00–15:00. Kiểm tra phản hồi API và màn hình bằng cả hai vai trò để xác nhận cùng kết quả và không có dữ liệu người mượn. Trên DB kiểm thử, đổi lượt 10:00–11:00 từ `HANDED_OVER` sang `RETURNED` rồi tra lại. Khoảng 11:00–13:00 mở rộng thành 10:00–13:00.

6. Với thiết bị demo có lịch trống toàn bộ, tra từ 09:00 ngày 16/11/2026 đến 09:00 ngày 16/11/2126 theo giờ CLB. Kiểm tra cả cửa sổ tra cứu và dòng kết quả đều hiện `09:00 16/11/2026 → 09:00 16/11/2126`.

### Kết quả Task #136

- Chrome headless qua HTTP cục bộ đã kiểm tra bản build với handler backend và kho dữ liệu tổng hợp trong bộ nhớ. Đã kiểm tra màn 360 px, múi giờ America/Los_Angeles, giá trị UTC gửi đi, lịch qua ngày và phần giây, đổi thiết bị trong khi tải, lượt cũ về sau, lịch bận toàn bộ, lỗi nhập, lỗi danh mục, thử lại sau 500, phản hồi 401/403/404 và tra cứu bằng hai vai trò.
- Lượt kiểm tra lại đạt `npm run build`, `npm test` (3/3) và `git diff --check`.
- Dùng kết quả SQL Server do bộ điều phối chạy ngoài sandbox trên cùng checkout, đạt 1/1 theo log `1794747349026653300-story-112-sqlserver.log`. Bài kiểm tra gồm migration, phiên, fixture lịch tổng hợp, khoảng bận chồng và nối tiếp, dữ liệu lịch trả về cho hai vai trò và việc giải phóng giờ khi chuyển sang đã trả.
- Xác minh trình duyệt qua Caddy HTTPS với cơ sở dữ liệu kiểm thử thuộc lượt kiểm tra triển khai. Caddy chưa có trên PATH trong môi trường này.

## Kết quả kiểm tra Task #120

- Chrome qua HTTPS đạt với API backend và kho dữ liệu tổng hợp trong bộ nhớ. Đã kiểm tra hai vai trò, đường dẫn trực tiếp, tải lại trang, phiên hết hạn, danh mục đang tải, rỗng, lỗi và thử lại, lỗi đăng xuất, làm mới CSRF và thu hồi phiên.
- `node --check frontend/app.js` và bộ kiểm thử HTTP của backend đạt. Handler quản lý thử nghiệm trả `403` cho thành viên trước khi thực thi.
- Theo kết quả người điều hành ghi trên Redmine #120, Chrome đã kiểm tra bản preview tại `localhost:3102` với cơ sở dữ liệu SQL Server demo riêng `ClubEquipmentLending_Preview`. Cả `demo.member` và `demo.manager` đều đăng nhập được, thấy `DEMO-01` và `DEMO-02`, giữ phiên khi tải lại và trở về màn đăng nhập khi đăng xuất. Lượt này chạy ngoài sandbox vì driver ODBC native không khả dụng trong sandbox.
