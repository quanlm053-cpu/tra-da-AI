# Xác minh SQL Server Story #111

Kiểm thử tích hợp Story #111 đã chạy ngoài sandbox trên đúng checkout bằng SQL Server thật, database ClubEquipmentLending_Test riêng. npm run test:sqlserver, npm test và npm run build đều exit 0. Bài SQL Server kiểm tra migration lặp lại, seed lặp lại, hai vai trò, hai thiết bị và vòng đời phiên. DEVOPS có thể dùng kết quả này để bàn giao. REVIEW/TESTER đọc bằng chứng và kiểm tra phần việc của mình; hạn chế ODBC trong sandbox không làm mất hiệu lực kết quả chạy ngoài sandbox khi các tệp SQL liên quan giữ nguyên.

SHA-256 tại lúc chạy:

- `backend/database.js`: `589cb32e915114845353a2349728f6f0474ac268829dbe4a62e711cb03b20af4`
- `backend/app.js`: `1551fe79aaf41069622972e1cdef41b433e98fc5724fc2d3793c850f4986cd40`
- `backend/migrations/001-foundation.sql`: `24294e9049c11842397f5ebc78a7cedf88561d6e5e44a370e7d612f256ae7d43`
- `backend/test/sqlserver.test.js`: `0233d6c0fdd39b70fde6ee8db178a9f51555962bf9335ed207ddcc836538f7c1`
- `package-lock.json`: `c4e414c1b5c140296bffa4c068ac642651293036cdc2b12381cef4ba6f6c4542`
