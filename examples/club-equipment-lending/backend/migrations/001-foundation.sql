IF OBJECT_ID(N'[__SCHEMA__].[users]', 'U') IS NULL
CREATE TABLE [__SCHEMA__].[users] (
    id int IDENTITY(1,1) PRIMARY KEY,
    username nvarchar(255) NOT NULL UNIQUE,
    password_hash varchar(255) NOT NULL,
    role varchar(16) NOT NULL CHECK (role IN ('MEMBER', 'MANAGER'))
);

IF OBJECT_ID(N'[__SCHEMA__].[sessions]', 'U') IS NULL
BEGIN
    CREATE TABLE [__SCHEMA__].[sessions] (
        token_hash binary(32) PRIMARY KEY,
        user_id int NOT NULL REFERENCES [__SCHEMA__].[users](id) ON DELETE CASCADE,
        expires_at datetime2(3) NOT NULL
    );
    CREATE INDEX sessions_expires_at_idx ON [__SCHEMA__].[sessions](expires_at);
END;

IF OBJECT_ID(N'[__SCHEMA__].[equipment]', 'U') IS NULL
CREATE TABLE [__SCHEMA__].[equipment] (
    id int IDENTITY(1,1) PRIMARY KEY,
    asset_code varchar(64) NOT NULL UNIQUE,
    name nvarchar(255) NOT NULL
);
