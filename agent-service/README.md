> Hướng dẫn triển khai Trà đá AI: xem [README ở thư mục gốc](../README.md). Các mục TicketLab là lịch sử kỹ thuật, không phải entrypoint của bản đóng gói.

# TicketLab: dịch vụ 5 agent

Chạy trên Windows bằng Python chuẩn và Codex CLI đang đăng nhập ChatGPT.
Không cần thêm OpenAI API key. Mức sử dụng phụ thuộc tài khoản Codex hiện tại.

`python controller.py doctor` kiểm tra kết nối, xác thực, repo và trạng thái.
`python controller.py run` chạy nền trong cửa sổ hiện tại.
`start.ps1` khởi động ẩn; `stop.ps1` yêu cầu dừng an toàn, hủy agent đang chạy.
`python controller.py status` xem tiến độ. Log và kết quả nằm trong runtime/.

Chỉ Story Selected mới được nhận. Các Story In Progress/Code Review có sẵn không tự bị nhận.
Một Story chạy tại một thời điểm: BA -> FE -> BE -> Review -> QA. Năm vai trò là năm
phiên Codex chuyên môn, không phải năm tiến trình luôn chạy cùng lúc.
Mỗi Story có nhánh/check-out riêng dưới runtime/worktrees. Không tự push GitHub.
Sau khi QA đạt, code được commit vào nhánh local và journal ghi đường dẫn, commit.

PM đổi Story sang Blocked thì tiến trình agent bị dừng; kết quả giai đoạn chưa được chấp nhận
được bỏ qua. Tiếp tục khi PM chuyển Blocked -> In Progress, giai đoạn sẽ chạy lại trên code
đã lưu. Không hoàn tác code dở dang. Nếu trạng thái đổi bất ngờ khác, dịch vụ ngừng xử lý
Story đó và ghi log để tránh ghi đè quyết định của con người.

Đóng Story cần Review và QA đạt, không còn child chưa Done. Child của PM không bị AI đóng.
BA lập kế hoạch cho child cũ, bổ sung Task mới khi thực sự thiếu. Người nhận hiện có được giữ;
Task mới giao cho thành viên theo vai trò trong config.json. Mọi journal AI có tiền tố vai trò.
Gateway và dịch vụ hiện dùng khóa Redmine của admin; vai trò AI là vai trò logic của controller,
không phải các tài khoản Redmine độc lập. Không tự thay đổi vai trò/quyền thành viên.

Trường hợp lỗi môi trường, hết hạn đăng nhập, hết hạn mức, timeout hoặc quá giới hạn sửa:
Story giữ nguyên giai đoạn, ghi journal cần PM xử lý, không chuyển Done và không tự lặp vô hạn.
Sau khi giải quyết, dùng `python controller.py retry STORY_ID` rồi chạy/để dịch vụ tiếp tục.
Chỉ retry công việc đã được dịch vụ nhận. Dịch vụ không sửa Backlog -> Selected thay PM.

Chuẩn bị môi trường test riêng (SQL Server, backend .env, frontend .env.local) trong checkout
của Story trước khi retry nếu QA báo thiếu. Không sao chép tự động secrets từ máy vào repo.
Dịch vụ truyền DB_NAME=TicketLab_AI_Test, backend 5101 và frontend 3101 cho agent để tách
khỏi ứng dụng đang dùng. Database test chưa được tự tạo và không được dùng database thật.
Giới hạn mặc định: 15 lượt agent/Story, 30 phút/lượt, 2 vòng sửa; xem config.json.

Dịch vụ chưa tự khởi động cùng Windows; phải chạy start.ps1 sau khi đăng nhập lại.
Chạy local trực tiếp qua localhost:3000 nên không phụ thuộc Cloudflare.

## Demo và sản phẩm theo từng Task

Mở http://localhost:8765 cạnh Redmine. Bảng chỉ đọc dữ liệu thật: agent đang làm,
Task/trạng thái/tiến độ, tệp đính kèm và báo cáo bàn giao. Không mô phỏng tiến độ.
Dịch vụ chạy Backend trước Frontend; sau đó review và QA. Các agent chạy theo lượt.

Mỗi completed_tasks trong kết quả AI phải có artifacts là đường dẫn tệp thật trong
checkout. Controller kiểm tra ownership/đường dẫn/kích thước, tạo ZIP gồm sản phẩm,
README, manifest SHA-256, kết quả kiểm tra và diff code; tài liệu văn bản được đính
kèm riêng để đọc trực tiếp. Sau khi upload và gắn vào đúng Task thành công mới đặt
100% và In Review. Không có sản phẩm thì không tự đóng Task. Không tải .env, khóa,
database dump, node_modules hoặc đường dẫn ngoài checkout. Retry cùng nội dung
không tạo thêm phiên bản trùng. Reviewer read-only có sản phẩm từ báo cáo JSON.

Task của PM vẫn cần con người nghiệm thu. SQL Server đã bị gỡ theo xác nhận PM;
build/test với mock không thay thế kiểm thử SQL Server thật và không cho Story Done.
Portable npm nằm trong tools/bin, không cài toàn cục. Dependencies cài bằng npm ci
--ignore-scripts; native SQL driver có thể cần cài/build riêng khi phục hồi môi trường DB.


## Direct office chat

The office on http://localhost:8766 sends scoped user requests to /api/chat on the local dashboard (8765). chat_queue.py persists and validates requests. The controller's single locked loop executes queued chat using the same scoped Codex tools and isolated Story checkout as workflow runs, then stores the model summary as the reply. Questions do not transition the workflow or replace prior implementation results. Completed task products retain ownership/path/evidence validation; BA plans must classify existing children before new tasks are created. Reviewer remains read-only. No automatic GitHub push/merge is enabled.

History: up to 50 rows displayed per Story; last eight completed exchanges for the selected role are included in each prompt. One queue item runs at a time. Restart interrupts an in-flight request as failed without replaying it. Move Story to Blocked to pause an executing agent under the existing controller policy. Changes made before interruption may remain in the checkout; inspect before asking to retry.


## Whole-team command, preview and GitHub

Choose CẢ ĐỘI or type `Cả đội làm Story 44` / `Tất cả làm task cha 44`. The inbox detects a start command, validates project/tracker/status and reactivates the existing checkpoint. New Backlog Stories move to Selected, then the normal BA pipeline claims them. Existing active jobs are not duplicated. Questions about team progress do not start work. Blocked/Done Stories and exhausted call/repair limits require PM action.

The team shares BA plans, requirements and previous_results between sequential specialist runs. Reviewer/QA defects become Redmine fix tasks and return the flow to Backend then Frontend. There is no unbounded or simultaneous write loop.

Frontend preview: loopback http://localhost:3101, API target http://localhost:5101/api. The preview manager does not stop an unknown process to reclaim a port. It starts frontend only; live database behavior requires the isolated QA backend/database. Templates prepare GitHub Actions UI smoke tests for each checkout.

GitHub is controller-owned: after independent local Review + QA, push `ai/story-<id>` to the configured origin, create/update a draft PR, wait for `ticketlab-ai-validation`, and turn failed CI into a repair handoff. Missing/cancelled/timeout CI is reported as infrastructure, not certified as a product bug. CI renders desktop/mobile screenshots and uploads artifacts; it does not replace SQL Server acceptance tests. No auto-merge. PM acceptance subtasks still gate Story Done.

Authentication uses the existing Git Credential Manager, read into memory only. On this machine run:

`git credential-manager github login --username quanlm053-cpu --device`

Use an account with push/PR/workflow permission for quanlm053-cpu/ticketlab_website. The service does not store or display the token. Until login is verified, no GitHub publish or cloud CI execution is claimed.


## Trà đá AI: thêm agent trong Office

Phần này dành cho /lending và lending/office.py, độc lập với workflow TicketLab bên dưới.

- Mở http://localhost:8766/lending, chọn **Agents → Thêm agent**. Điền tên, nhiệm vụ, chuyên môn mẫu, hướng dẫn và quyền đọc/sửa code. Hệ thống tự tạo tài khoản Redmine riêng, thêm vào dự án và gán vai trò; không chọn lại người cũ.
- Hồ sơ dùng bốn tab: **Profile** (vai trò, mô tả, mục tiêu, hướng dẫn, quy tắc, tags); **Runtime** (Codex/model/effort/quyền/timeout/lượt đồng thời); **Capabilities** (skill và công cụ); **Collaboration** (người được hỏi/giao việc, tự chủ, đề xuất nhân sự và giới hạn phân công).
- Runtime hỗ trợ Codex CLI, Claude Code và Gemini CLI theo từng agent, cho cả task, chat và tư vấn. Cấu hình cũ giữ mặc định Codex; đổi provider sẽ xóa model cũ trong biểu mẫu để tránh nhầm nhà cung cấp. Gợi ý model Codex đọc từ cache; Claude/Gemini có alias/gợi ý và cho điền ID riêng. Danh sách không cam kết quyền truy cập tài khoản.
- CLI Claude 2.1.332 và Gemini 0.71.1 được ghim phiên bản trong tools/providers/package-lock.json, có thể cài bằng provider.ps1 -Action install. Claude dùng native executable trong gói npm theo kiến trúc; Gemini dùng Node chạy bundle. Không chạy shim .cmd bằng shell với đối số tác vụ. Profile không được chứa executable, endpoint hay API key.
- Các agent dùng hạn mức của tài khoản nhà cung cấp tương ứng; có giới hạn token tháng theo agent trong dashboard Quản lý token, chưa quy đổi ngân sách tiền. Không tự fallback sang provider khác. CLI thiếu, chưa có dấu hiệu đăng nhập, lỗi API hoặc bàn giao sai cấu trúc đều báo lỗi rõ, không tự thực hiện action.
- Claude dùng restricted mode, strict MCP riêng của lượt, tool allowlist và dontAsk; không bật bypassPermissions. Gemini dùng phiên riêng với CLI_HOME và workspace điều khiển tạm, nạp user/workspace settings hợp lệ, core/allowed tools, chỉ MCP Lending, tắt hooks/extensions/subagents. Node launcher đọc key từ kho CLI gốc rồi truyền qua môi trường tiến trình con; không ghi key vào settings/log. Thư mục dự án thật được thêm bằng include-directories. Không dùng file system-settings do người dùng tạo, vì Gemini CLI yêu cầu file quản trị viên và có thể bỏ qua nó. Chế độ chỉ đọc của hai provider này không bật shell hoặc native edit/write; công cụ đọc Redmine được lọc lại tại MCP server.
- Claude dùng structured_output; Gemini dùng JSON response, được kiểm tra theo đầy đủ schema bàn giao mà hệ thống tạo (required, type, enum, additionalProperties, arrays, minimum). Kết quả lỗi/sai định dạng không được chuyển thành action PM. Stdout nhà cung cấp và stderr/log tách riêng; output cuối cùng chuẩn hóa như Codex.
- Không thay đổi đăng nhập toàn máy từ giao diện. Nút Kiểm tra cài đặt chỉ gọi --version và Claude auth status khi phù hợp, không gửi prompt/model request. credential_detected là dấu hiệu cấu hình, KHÔNG phải đã kiểm chứng quyền dùng model. Lần chạy thật mới xác nhận model/auth/quota.
- Runtime thực sự truyền model và effort xuống CLI, áp dụng timeout 1–180 phút và giới hạn 1–8 lượt gọi đồng thời mỗi agent. Các lượt ghi có thư mục giao nhau phải chờ nhau. Đây là trần lượt gọi, không tự mở thêm task hoặc tăng số worker triển khai.
- Skill nền theo chuyên môn vẫn được nạp; skill bổ sung lấy từ thư viện của dự án. Có thể viết và gắn skill mới trên giao diện (tối đa 32.000 ký tự/skill). Goals/rules/description/role và skill được đưa vào prompt. Tags dùng để tìm kiếm, không tự cấp quyền.
- Công cụ mặc định: Terminal và ba công cụ đọc Redmine. Bỏ mặc định để chọn riêng. Terminal điều khiển shell_tool của Codex, tìm web điều khiển web_search; công cụ Redmine bị bỏ không được liệt kê và bị MCP từ chối nếu vẫn gọi. Quyền sửa file được kiểm soát bằng sandbox ở Runtime, độc lập với Terminal; tắt Terminal không đồng nghĩa tắt mọi cách sửa file.
- Hỏi chuyên môn và phân công là hai quyền riêng. Mặc định agent mới chỉ được hỏi đội ngũ, không giao task. Khi được cấp quyền phân công, model có thể trả đề xuất có cấu trúc; bộ điều phối kiểm tra người nhận sẵn sàng, dự án, độ sâu 1–5 và giới hạn đề xuất/task con đang mở. Đề xuất có ID ổn định để tránh thực hiện trùng.
- Mức tự chủ Theo dự án mặc định chờ người dùng duyệt; chế độ tự phân công chỉ thực hiện ngay task độc lập trong quyền đã cấp. Công việc phụ thuộc chờ công việc gốc hoàn thành trước khi tạo task để tránh chu trình đóng Story. PM cũ mặc định tiếp tục điều phối như trước; đổi PM sang chế độ đề xuất sẽ đưa phương án vào hàng duyệt (lệnh dừng dự án luôn được xử lý).
- **Agents → chọn agent → Đề xuất chờ duyệt** cho phép duyệt/từ chối. Đề xuất agent mới luôn cần duyệt và chỉ tạo hồ sơ nháp quyền đọc cùng tài khoản Redmine; không tự kích hoạt nhân sự hoặc chạy model. Agent liên quan tới đề xuất đang mở không được lưu trữ/xóa trước khi xử lý đề xuất.
- **Tạo agent** lưu bản nháp và đồng bộ Redmine ở nền. **Kiểm tra & kích hoạt** kiểm tra Codex CLI/hướng dẫn rồi kích hoạt tài khoản Redmine. Agent chỉ được nhận việc sau khi xác minh user, trạng thái và membership; bước này không gọi model hay tiêu token. Đăng nhập/model được xác nhận ở lượt chạy thực tế.
- Chọn agent đã sẵn sàng, nhập mã Story hiện có để giao task, hoặc yêu cầu PM giao việc theo tên agent. PM nhận ID và chuyên môn của những agent sẵn sàng. Agent mới không tự xuất hiện trong mọi pipeline.
- Agent chỉ đọc bàn giao báo cáo lên task Redmine và không xuất bản code. Agent có quyền sửa code dùng checkout của task, đi qua REVIEW, TESTER và CI trước khi merge như hiện có. Các lượt triển khai vẫn theo hàng đợi hiện tại, chưa tự tăng số luồng ghi code.
- Tên hiển thị và ID độc lập; có thể tạo FE-02 cùng chuyên môn Frontend. Mỗi dự án lưu hồ sơ riêng tại thư mục runtime của dự án, trong agents.json. Không đặt token vào hồ sơ.
- **Tạm dừng / Tiếp tục** điều khiển việc nhận lượt mới và đồng bộ khóa/kích hoạt tài khoản Redmine riêng. Lượt đang chạy phải bàn giao xong trước khi đổi hồ sơ. **Lưu trữ** hoặc **Chấm dứt hoạt động** yêu cầu không còn task/hội thoại chờ. Chấm dứt cần nhập đúng tên và gỡ token Discord lưu cục bộ. Phiên bot đang mở hoặc token trên Discord phải được dừng/reset riêng.
- **Khôi phục** đưa agent đã lưu trữ/chấm dứt về bản nháp, giữ ID và lịch sử; cần kiểm tra lại trước khi nhận việc. Có thể sửa tên khi đang lưu trữ để xử lý trùng tên. Giới hạn 24 agent được kiểm tra cả khi tạo và khôi phục.
- **Xóa vĩnh viễn** chỉ dành cho agent bổ sung đã lưu trữ/chấm dứt, không còn việc chờ, và cần nhập đúng tên. Hồ sơ/hướng dẫn trong danh sách quản lý bị xóa; tên/ID tối thiểu và nhật ký thay đổi được giữ để đối chiếu task, hội thoại và bản bàn giao cũ. Không xóa issue Redmine, repo, ứng dụng Discord hay nhật ký công việc đã tạo. Không có nút khôi phục hồ sơ đã xóa.
- **Nhân bản agent** sao chép chuyên môn/hướng dẫn/quyền/ánh xạ Redmine sang ID mới ở trạng thái nháp, không sao chép token. PM không được nhân bản. Tám agent gốc được bảo vệ khỏi lưu trữ/chấm dứt/xóa vì pipeline cũ còn tham chiếu chúng.
- Có tìm kiếm theo tên/chuyên môn, lọc trạng thái, hoàn tác sửa chưa lưu và lịch sử thay đổi. Lưu hồ sơ dùng số phiên bản để phát hiện xung đột. Nhật ký chỉ ghi loại thay đổi và tên trường, không chép nội dung hướng dẫn hay token.
- Có thể chuyển task riêng chưa bắt đầu sang agent sẵn sàng cùng chuyên môn và quyền; người nhận được cập nhật và xác minh trên Redmine. Task đang chạy/đã bàn giao không bị tự ý chuyển. Yêu cầu hội thoại còn trong hàng chờ có thể hủy trước khi lưu trữ agent.
- Nhân vật, Focus, trạng thái, nhãn bàn giao và số lượng agent trên Office đọc cùng hồ sơ. Văn phòng hỗ trợ tối đa 24 agent chưa lưu trữ.
- Discord không bắt buộc. Với bot mới đã thêm vào server, chạy discord_pm.py --agents SA BA FE BE TESTER REVIEW DEVOPS --custom-agents AGENT_ID, thay AGENT_ID bằng mã trong panel. Token của agent mới được hỏi một lần và lưu bằng ID ổn định trong Windows Credential Manager. Khởi động lại riêng bot Discord để nhận danh sách mới; không cần nhập lại token cũ.
- Tài khoản dịch vụ Redmine cần quyền admin để tạo user và quản lý membership. Login dùng ID ổn định theo dự án, không phụ thuộc tên hiển thị; password ngẫu nhiên không được lưu/hiển thị/gửi email. Hoạt động Redmine vẫn do bộ điều phối thực thi bằng tài khoản dịch vụ, tài khoản riêng dùng để nhận việc và giữ lịch sử.
- Tên, quyền dự án và trạng thái user được xác minh sau khi đồng bộ; bản nháp/tạm dừng/lưu trữ dùng user khóa, agent sẵn sàng dùng user hoạt động. Khi xóa hồ sơ, user Redmine được xác minh đã khóa và được giữ để bảo toàn lịch sử.
- Lỗi đồng bộ hiện rõ trong hồ sơ, có nút thử lại và tự thử lại sau 60 giây. ID user được ghi lại trước bước thêm thành viên để phục hồi sau lỗi mạng/khởi động lại, không tạo user trùng. Hồ sơ cũ từng dùng người nhận chung được chuyển sang tài khoản riêng; chỉ cập nhật task còn chờ, không sửa tài khoản người cũ hoặc task đã bàn giao. Nếu task đã được đổi người nhận thủ công, hệ thống báo cần kiểm tra thay vì ghi đè.
- Tài khoản model và ứng dụng Discord không được tạo tự động; các kết nối này vẫn cần đăng nhập/token riêng.

Kiểm thử riêng: python -m unittest discover -s agent-service/lending -p "test_agent*.py" -v.

Định dạng agents.json phiên bản 2 chứa agents, deleted (thông tin đối chiếu tối thiểu) và events; redmine_sync giữ thông tin phục hồi, không có mật khẩu. Hồ sơ cũ được đọc với cấu hình mặc định tương thích; chỉ cập nhật bản lưu khi người dùng lưu. API state trả agent_management_version=4; giao diện báo cần khởi động lại backend nếu chưa nhận được phiên bản này. Chỉ cần nạp lại dịch vụ sau khi sửa mã backend; thêm/sửa agent thường ngày không cần restart.

## Parallel specialist wave (TicketLab)

When parallel_enabled=true, after the initial BA plan, dev stages migrate to a parallel wave. Backend and Frontend implement in independent detached Git worktrees overlaid with the current dirty source. BA reviews requirements support, QA prepares the test matrix, and Reviewer performs a preliminary baseline risk audit concurrently. Those support passes do not complete their acceptance/review tasks. A final Reviewer pass and final integrated QA still execute after the merge.

The owner thread reserves five calls, persists running_roles, and alone updates Redmine or promotes source. Worker threads each own a separate Service/database connection and only return results. No shared writable node_modules or implementation checkout. Ownership checks reject cross-role edits; changed files are compared against the original main snapshot and conflicts stop promotion. Isolated worktrees/results remain under runtime/parallel for recovery. Products are attached only from the merged canonical tree. Parallel mode allows up to 30 total specialist calls per Story and retains the configured two repair rounds.

Verified: actual two-thread barrier test on independent Git worktrees, ownership rejection, preserving concurrent human edits, and the existing workflow/product/chat/CI suite (36 tests).


## QA sandbox SQL/port recovery

Restricted Windows agent tokens may fail native ODBC TLS despite the same encrypted connection succeeding under the controller. Do not disable encryption or relax the sandbox. test_bridge.py and test_db_bridge.cjs expose only fixed operations for synthetic Story 44 fixtures in TicketLab_AI_Test. They require a random local capability passed only to final QA, reject arbitrary SQL and production database selection, and never return real DB credentials. Status includes actual encrypt_option and managed frontend/backend HTTP readiness. Fixtures can be created, read, constrained stock/price adjusted, targeted rollback triggers toggled, and cleaned; all operations are scoped by controller-owned fixture IDs. The app's normal public backend API remains the subject under test.

QA uses scripts/story-44-qa-preflight.cjs and story-44-test-fixtures.cjs rather than Get-NetTCPConnection or direct ODBC from the restricted process. A passing preflight or controller smoke is not Story acceptance. Full T01-T15 evidence and independent review remain required.


### Kết nối nhà cung cấp cho agent

Tại thư mục gốc dự án:

    powershell -ExecutionPolicy Bypass -File ".\\agent-service\\lending\\provider.ps1" -Provider claude -Action status
    powershell -ExecutionPolicy Bypass -File ".\\agent-service\\lending\\provider.ps1" -Provider gemini -Action status

Chưa có CLI thì đổi Action thành install; muốn đăng nhập thì dùng Action login. Claude mở luồng auth login của CLI; Gemini mở CLI tương tác để chọn đăng nhập Google. API key dùng môi trường của tiến trình backend: ANTHROPIC_API_KEY (Claude), GEMINI_API_KEY (Gemini); không ghi key trong agent/skill, repo hay log. Khi đổi biến môi trường, mở lại backend từ phiên shell có biến đó. Đăng nhập CLI đã lưu được dùng lại mà không nhập mỗi task.

Trong Agents → Runtime chọn nhà cung cấp và model, lưu bản nháp, sau đó Kiểm tra & kích hoạt khi đã cấu hình tài khoản. Việc kích hoạt kiểm tra cài đặt/dấu hiệu auth; không có model call kiểm tra mất phí. Quyền model chỉ được xác nhận khi thực thi. Agent mới chưa có auth vẫn được lưu để cấu hình sau.

Tài liệu adapter: https://code.claude.com/docs/en/cli-reference và https://geminicli.com/docs/reference/configuration/. Không cần Claude/Gemini để các agent Codex cũ tiếp tục chạy. Nạp bản backend mới một lần sau cập nhật mã; các lần thêm/sửa runtime không cần restart (trừ khi đổi môi trường/auth mà tiến trình cần nạp lại).


### Danh sách và thử model Gemini thực tế
- Gemini không còn gợi ý model viết cứng. Runtime gọi GET /lending-api/agents/models; bridge Node đọc key từ môi trường GEMINI_API_KEY hoặc kho key của Gemini CLI, rồi gọi Google models.list có phân trang. Chỉ trả model Gemini có generateContent phù hợp tác vụ văn bản; key nằm trong header gửi tới đúng Google API, không đi qua Python/browser/log hay URL.
- Kết quả danh sách ghi source=google_api, generation_tested=false, verified=false; không đồng nghĩa có quyền, còn quota hoặc còn được phục vụ khi gọi. Nếu lỗi auth/quota/network, hiển thị lỗi và bỏ danh sách cũ, không fallback gợi ý giả.
- Nút Thử model đã chọn gửi POST cùng Origin hợp lệ, một prompt cố định không chứa dữ liệu dự án, không tools/file, tối đa 512 output token. Có thể tiêu quota/chi phí API. Chỉ verified=true khi nhận được văn bản thực tế; trả thống kê token nếu Google cung cấp. Không tự thử khi mở panel/lấy danh sách, không tự đổi model.
- 400/401/403/404/429, phản hồi không có nội dung và timeout đều không được báo thành công. Thử này xác nhận API/model, chưa xác nhận toàn bộ tác vụ CLI/MCP của agent. Kết quả trên UI được xóa khi đổi agent/provider/model hoặc làm mới danh sách.
- OAuth đơn thuần chưa hỗ trợ models.list trong bridge này; cần API key đã lưu hoặc GEMINI_API_KEY. Khóa do CLI lưu vẫn được tái sử dụng, không cần nhập lại trong Office.


### Kiểm thử runtime agent thực tế
Trong Runtime có nút Thử luồng agent thực tế (tốn token thật, tối đa 90 giây, một lượt thử đồng thời). POST /lending-api/agents/runtime-test chỉ nhận Origin Office và JSON. Lượt thử không tạo agent/task, không đổi dự án hoặc trạng thái tạm dừng.

Agent phải đọc token ngẫu nhiên từ file trong workspace riêng, gọi MCP fixture chỉ đọc (không kết nối Redmine), trả token MCP đúng và JSON bàn giao hợp lệ. Với quyền write phải tạo result.txt có nội dung chính xác; với read phải giữ nguyên file. Kết quả không dựa riêng vào lời model báo thành công. Workspace kiểm thử tự dọn khi hoàn tất/thất bại; không ghi khóa bí mật vào hồ sơ.

Gemini CLI dùng phiên riêng để tránh sửa .gemini/settings.json của repo hoặc tài khoản. Chỉ phiên điều khiển tự tạo được đánh dấu trusted; file task đặt trong workspace được include rõ. Lượt thử giới hạn công cụ read_file/write_file + MCP fixture, không shell/GitHub/network tool. Với lượt thử, giới hạn sinh đầu ra mỗi lượt và mức suy luận nhẹ trên model hỗ trợ, không thay cấu hình agent đã lưu.

Khi CLI báo quota, lỗi xác thực, quá tải 503 hoặc từ chối cấu hình, controller dừng cây tiến trình thay vì để SDK retry mãi. Kết quả chưa đạt hiển thị lỗi; không tự chuyển model/provider. Chưa có tài khoản Claude Code hợp lệ thì lượt kiểm thử Claude dừng trước khi gọi model.

### Quản lý token
Office → Quản lý token trên thanh điều hướng: bảng tổng quan cả đội, lọc tháng/provider, tìm agent, biểu đồ ngày và bảng xếp theo lượng dùng. Bấm agent để xem lượt chạy và giới hạn tháng (0 = không giới hạn). Dữ liệu lưu riêng từng dự án trong runtime/token-usage.json, giữ qua khởi động lại; tháng theo UTC+7. GET /lending-api/agents/tokens trả thống kê; POST cùng đường dẫn chỉ nhận Origin Office, agent hợp lệ và limit nguyên 0–1 tỷ.

Mỗi lượt gọi model thực thi/chat/tham vấn qua Office ghi usage CLI, kể cả lượt lỗi nếu có số liệu. Cache nằm trong đầu vào, không cộng hai lần. Gemini tổng gồm suy luận. Không ước lượng token từ độ dài văn bản; không có usage hiển thị chưa xác định. Không truy hồi phiên cũ, không gồm nút thử model/runtime, phiên CLI bên ngoài Office, hóa đơn hay quota nhà cung cấp.

Giới hạn kiểm tra trước mỗi lượt, chặn khi tổng tháng đạt ngưỡng. Không cắt model đang chạy nên có thể vượt ngưỡng. Khi bật giới hạn, một agent chỉ có một lượt đang ghi nhận và lượt thiếu usage cũng chặn lượt mới để không âm thầm bỏ qua hạn mức. Có thể tăng ngưỡng hoặc đặt 0 để bỏ giới hạn; không xóa lịch sử. Backend cần khởi động lại để nạp tính năng.
