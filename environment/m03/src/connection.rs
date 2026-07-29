use rusqlite::{Connection, OpenFlags};
use m01_seal::VaultError;

pub fn open_connection(path: &str) -> Result<Connection, VaultError> {
    let flags = OpenFlags::SQLITE_OPEN_READ_WRITE
        | OpenFlags::SQLITE_OPEN_CREATE
        | OpenFlags::SQLITE_OPEN_FULL_MUTEX;
    Connection::open_with_flags(path, flags).map_err(VaultError::from)
}
