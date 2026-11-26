IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE object_id = OBJECT_ID(N'[__SCHEMA__].[loan_requests]', 'U')
      AND name = N'UX_loan_requests_equipment_handed_over'
)
BEGIN
    IF EXISTS (
        SELECT equipment_id FROM [__SCHEMA__].[loan_requests] WITH (TABLOCKX, HOLDLOCK)
        WHERE status = 'HANDED_OVER'
        GROUP BY equipment_id HAVING COUNT(*) > 1
    ) THROW 51044, 'Multiple active holders for the same equipment. Verify the existing loan records.', 1;

    CREATE UNIQUE INDEX UX_loan_requests_equipment_handed_over
        ON [__SCHEMA__].[loan_requests] (equipment_id)
        WHERE status = 'HANDED_OVER';
END;
