IF OBJECT_ID(N'[__SCHEMA__].[loan_requests]', 'U') IS NULL
BEGIN
    CREATE TABLE [__SCHEMA__].[loan_requests] (
        id int IDENTITY(1,1) PRIMARY KEY,
        equipment_id int NOT NULL REFERENCES [__SCHEMA__].[equipment](id),
        borrower_id int NOT NULL REFERENCES [__SCHEMA__].[users](id),
        start_at datetime2(3) NOT NULL,
        end_at datetime2(3) NOT NULL,
        status varchar(16) NOT NULL CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'HANDED_OVER', 'RETURNED')),
        created_at datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        CHECK (start_at < end_at)
    );
    CREATE INDEX loan_requests_availability_idx
        ON [__SCHEMA__].[loan_requests](equipment_id, status, start_at) INCLUDE (end_at);
END;
