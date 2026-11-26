IF OBJECT_ID(N'[__SCHEMA__].[loan_events]', 'U') IS NULL
BEGIN
    CREATE TABLE [__SCHEMA__].[loan_events] (
        id bigint IDENTITY(1,1) PRIMARY KEY,
        request_id int NOT NULL REFERENCES [__SCHEMA__].[loan_requests](id),
        actor_id int NOT NULL REFERENCES [__SCHEMA__].[users](id),
        from_status varchar(16) NOT NULL,
        to_status varchar(16) NOT NULL,
        occurred_at datetime2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
        CHECK (
            (from_status = 'PENDING' AND to_status IN ('APPROVED', 'REJECTED'))
            OR (from_status = 'APPROVED' AND to_status = 'HANDED_OVER')
            OR (from_status = 'HANDED_OVER' AND to_status = 'RETURNED')
        )
    );
    CREATE INDEX loan_events_request_idx ON [__SCHEMA__].[loan_events](request_id, id);
    CREATE INDEX loan_requests_queue_idx ON [__SCHEMA__].[loan_requests](status, created_at, id);
END;
