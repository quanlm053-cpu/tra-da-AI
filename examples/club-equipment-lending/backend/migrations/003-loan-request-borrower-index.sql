IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'[__SCHEMA__].[loan_requests]', 'U')
      AND name = N'loan_requests_borrower_idx'
)
BEGIN
    CREATE INDEX loan_requests_borrower_idx
        ON [__SCHEMA__].[loan_requests](borrower_id, created_at DESC, id DESC)
        INCLUDE (equipment_id, start_at, end_at, status);
END;
