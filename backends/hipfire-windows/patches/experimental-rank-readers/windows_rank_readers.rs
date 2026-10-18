//! Experimental Windows-only synchronous file objects for rank-table reads.
//!
//! One reader preserves the exact borrowed-anchor path. More readers reopen
//! that anchor eagerly, without resolving its pathname or sharing its cursor.
#![cfg(windows)]

use std::ffi::{c_void, OsStr};
use std::fs::File;
use std::io;
use std::os::windows::io::{AsRawHandle, FromRawHandle};
use std::sync::{Condvar, Mutex};

pub const ENV_NAME: &str = "HIPFIRE_WINDOWS_PLE_READERS";
const MAX_READERS: usize = 64;
const GENERIC_READ: u32 = 0x8000_0000;
const SHARE_READ_WRITE_DELETE: u32 = 1 | 2 | 4;

#[link(name = "kernel32")]
unsafe extern "system" {
    fn ReOpenFile(original: *mut c_void, access: u32, share: u32, flags: u32) -> *mut c_void;
}

fn invalid_count() -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, format!("{ENV_NAME} must be ASCII decimal 1..64"))
}

/// Absent means one; otherwise accept only nonempty ASCII digits in 1..=64.
/// Leading zeroes are decimal digits, not a sign, whitespace or another radix.
pub fn parse_reader_count(value: Option<&OsStr>) -> io::Result<usize> {
    let Some(value) = value else { return Ok(1); };
    let value = value.to_str().ok_or_else(invalid_count)?;
    if value.is_empty() { return Err(invalid_count()); }
    let mut count = 0usize;
    for byte in value.bytes() {
        if !byte.is_ascii_digit() { return Err(invalid_count()); }
        count = count.checked_mul(10).and_then(|n| n.checked_add(usize::from(byte - b'0')))
            .ok_or_else(invalid_count)?;
        if count > MAX_READERS { return Err(invalid_count()); }
    }
    if count == 0 { return Err(invalid_count()); }
    Ok(count)
}

enum Pool {
    Anchor,
    Reopened(SharedPool),
}

struct SharedPool {
    count: usize,
    available: Mutex<Vec<File>>,
    returned: Condvar,
}

/// A fixed-capacity pool. Construction performs every reopen before publishing
/// the pool; dropping a partially built Vec closes all successfully opened files.
pub struct RankReaderPool {
    pool: Pool,
}

impl RankReaderPool {
    pub fn from_env(anchor: &File) -> io::Result<Self> {
        Self::new(anchor, parse_reader_count(std::env::var_os(ENV_NAME).as_deref())?)
    }

    pub fn new(anchor: &File, count: usize) -> io::Result<Self> {
        if !(1..=MAX_READERS).contains(&count) { return Err(invalid_count()); }
        if count == 1 { return Ok(Self { pool: Pool::Anchor }); }

        let mut files = Vec::with_capacity(count);
        for _ in 0..count {
            // SAFETY: anchor is borrowed and valid throughout ReOpenFile. Flags
            // zero requests synchronous buffered I/O, without OVERLAPPED or hints.
            let raw = unsafe {
                ReOpenFile(anchor.as_raw_handle(), GENERIC_READ, SHARE_READ_WRITE_DELETE, 0)
            };
            if raw == (-1isize) as *mut c_void || raw.is_null() {
                return Err(io::Error::last_os_error());
            }
            // SAFETY: this successful ReOpenFile result is a new owned handle;
            // ownership is transferred exactly once, including on later failure.
            files.push(unsafe { File::from_raw_handle(raw) });
        }
        Ok(Self { pool: Pool::Reopened(SharedPool {
            count,
            available: Mutex::new(files),
            returned: Condvar::new(),
        }) })
    }

    pub fn count(&self) -> usize {
        match &self.pool { Pool::Anchor => 1, Pool::Reopened(pool) => pool.count }
    }

    /// `anchor` is the same store-owned anchor passed at construction. The one
    /// reader case borrows it directly; no lock or reopen occurs in this branch.
    /// A multi-reader lease owns one file while performing I/O, with no lock held.
    pub fn acquire<'a>(&'a self, anchor: &'a File) -> io::Result<ReaderLease<'a>> {
        let pool = match &self.pool {
            Pool::Anchor => return Ok(ReaderLease { source: LeaseSource::Anchor(anchor) }),
            Pool::Reopened(pool) => pool,
        };
        let poisoned = || io::Error::new(io::ErrorKind::Other, "rank-reader pool mutex poisoned");
        let mut available = pool.available.lock().map_err(|_| poisoned())?;
        loop {
            if let Some(file) = available.pop() {
                drop(available);
                return Ok(ReaderLease { source: LeaseSource::Reopened { pool, file: Some(file) } });
            }
            available = pool.returned.wait(available).map_err(|_| poisoned())?;
        }
    }
}

enum LeaseSource<'a> {
    Anchor(&'a File),
    Reopened { pool: &'a SharedPool, file: Option<File> },
}

/// Returns its one owned reader on normal return, I/O error, EOF or unwinding.
/// Rust's borrow prevents the pool from being dropped while any lease is live.
pub struct ReaderLease<'a> {
    source: LeaseSource<'a>,
}

impl ReaderLease<'_> {
    pub fn file(&self) -> &File {
        match &self.source {
            LeaseSource::Anchor(file) => file,
            LeaseSource::Reopened { file, .. } => file.as_ref().expect("live reader lease"),
        }
    }
}

impl Drop for ReaderLease<'_> {
    fn drop(&mut self) {
        if let LeaseSource::Reopened { pool, file } = &mut self.source {
            if let Some(file) = file.take() {
                // Return ownership even if an unrelated panic poisoned the lock;
                // Drop must not panic and lose capacity during another unwind.
                let mut available = pool.available.lock().unwrap_or_else(|error| error.into_inner());
                available.push(file);
                drop(available);
                pool.returned.notify_one();
            }
        }
    }
}
