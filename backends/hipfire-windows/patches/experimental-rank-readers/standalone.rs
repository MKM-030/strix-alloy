// Standalone Windows CPU fixtures. Execution is deliberately deferred to root.
// This harness opens only the small temporary files it creates itself.
#[cfg(not(windows))]
compile_error!("The rank-reader fixtures require native Windows; a zero-test non-Windows run is invalid.");

#[cfg(windows)]
mod windows_rank_readers;

#[cfg(windows)]
fn main() {}

#[cfg(all(test, windows))]
mod tests {
    use super::windows_rank_readers::{parse_reader_count, RankReaderPool, ENV_NAME};
    use std::ffi::{c_void, OsStr, OsString};
    use std::fs::{self, File, OpenOptions};
    use std::io::{self, ErrorKind, Read, Seek, SeekFrom, Write};
    use std::os::windows::ffi::OsStringExt;
    use std::os::windows::fs::{FileExt, OpenOptionsExt};
    use std::os::windows::io::AsRawHandle;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::{Arc, Barrier, Mutex};

    // Serializes this harness's environment changes and stale-handle checks.
    // Worker threads inside a test still perform concurrent leased reads.
    static FIXTURE_LOCK: Mutex<()> = Mutex::new(());
    static NEXT_DIRECTORY: AtomicUsize = AtomicUsize::new(0);
    const SHARE_ALL: u32 = 1 | 2 | 4;

    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn LockFile(file: *mut c_void, low: u32, high: u32, len_low: u32, len_high: u32) -> i32;
        fn UnlockFile(file: *mut c_void, low: u32, high: u32, len_low: u32, len_high: u32) -> i32;
        fn GetHandleInformation(handle: *mut c_void, flags: *mut u32) -> i32;
    }

    struct Fixture {
        directory: PathBuf,
        path: PathBuf,
    }

    impl Fixture {
        fn new(bytes: &[u8]) -> io::Result<Self> {
            let directory = loop {
                let serial = NEXT_DIRECTORY.fetch_add(1, Ordering::Relaxed);
                let candidate = std::env::temp_dir().join(format!(
                    "hipfire-rank-readers-{}-{serial}", std::process::id()
                ));
                match fs::create_dir(&candidate) {
                    Ok(()) => break candidate,
                    Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
                    Err(error) => return Err(error),
                }
            };
            let fixture = Self { path: directory.join("rows.bin"), directory };
            OpenOptions::new().write(true).create_new(true).open(&fixture.path)?.write_all(bytes)?;
            Ok(fixture)
        }

        fn anchor(&self) -> io::Result<File> {
            OpenOptions::new().read(true).write(true).share_mode(SHARE_ALL).open(&self.path)
        }
    }

    impl Drop for Fixture {
        fn drop(&mut self) {
            // Remove only the two known fixture filenames, never a recursive tree.
            let _ = fs::remove_file(&self.path);
            let _ = fs::remove_file(self.directory.join("renamed.bin"));
            let _ = fs::remove_dir(&self.directory);
        }
    }

    struct RestoreEnvironment(Option<OsString>);

    impl Drop for RestoreEnvironment {
        fn drop(&mut self) {
            // This is the sole environment-using test, under FIXTURE_LOCK.
            unsafe {
                match self.0.take() {
                    Some(value) => std::env::set_var(ENV_NAME, value),
                    None => std::env::remove_var(ENV_NAME),
                }
            }
        }
    }

    struct FileLock<'a>(&'a File);

    impl<'a> FileLock<'a> {
        fn first_byte(file: &'a File) -> io::Result<Self> {
            // LockFile locks this byte against reads through other file handles.
            let result = unsafe { LockFile(file.as_raw_handle(), 0, 0, 1, 0) };
            if result == 0 { return Err(io::Error::last_os_error()); }
            Ok(Self(file))
        }
    }

    impl Drop for FileLock<'_> {
        fn drop(&mut self) {
            // The borrowed file outlives this exact one-byte lock.
            let _ = unsafe { UnlockFile(self.0.as_raw_handle(), 0, 0, 1, 0) };
        }
    }

    // Local consumer fixture, not a replacement for the product's exact-read loop.
    // seek_read can be short and changes the cursor; every call uses its own offset.
    fn read_exact_positioned(file: &File, offset: u64, output: &mut [u8]) -> io::Result<()> {
        let mut done = 0;
        while done < output.len() {
            let at = offset.checked_add(done as u64)
                .ok_or_else(|| io::Error::new(ErrorKind::InvalidInput, "fixture offset overflow"))?;
            match file.seek_read(&mut output[done..], at) {
                Ok(0) => return Err(io::Error::new(ErrorKind::UnexpectedEof, "truncated fixture range")),
                Ok(count) => done += count,
                Err(error) if error.kind() == ErrorKind::Interrupted => {}
                Err(error) => return Err(error),
            }
        }
        Ok(())
    }

    fn handle_is_open(handle: usize) -> bool {
        let mut flags = 0;
        // Query only; this neither closes nor adopts the captured handle value.
        unsafe { GetHandleInformation(handle as *mut c_void, &mut flags) != 0 }
    }

    #[test]
    fn parsing_default_borrow_and_explicit_capacity_obey_the_contract() -> io::Result<()> {
        // Catches an accidental changed default, off-by-one bound, or trim/sign parser.
        assert_eq!(parse_reader_count(None).unwrap(), 1);
        for count in 1..=64 {
            assert_eq!(parse_reader_count(Some(OsStr::new(&count.to_string()))).unwrap(), count);
        }
        assert_eq!(parse_reader_count(Some(OsStr::new("0001"))).unwrap(), 1);
        assert_eq!(parse_reader_count(Some(OsStr::new("064"))).unwrap(), 64);
        for invalid in ["", "0", "00", "65", "100", "18446744073709551616000", "-1", "+1",
                        " 1", "1 ", "\t2", "2\n", "1.0", "0x10", "1_0", "１", "١", "1\0"] {
            assert_eq!(parse_reader_count(Some(OsStr::new(invalid))).unwrap_err().kind(),
                       ErrorKind::InvalidInput, "accepted {invalid:?}");
        }
        let non_unicode = OsString::from_wide(&[0xD800]);
        assert_eq!(parse_reader_count(Some(&non_unicode)).unwrap_err().kind(), ErrorKind::InvalidInput);
        // Catches reopening/duplicating or accidentally closing the default anchor.
        let _serial = FIXTURE_LOCK.lock().unwrap();
        let fixture = Fixture::new(b"0123456789abcdef")?;
        let anchor = fixture.anchor()?;
        let original = anchor.as_raw_handle();
        let pool = RankReaderPool::new(&anchor, 1)?;
        assert_eq!(pool.count(), 1);
        let lease = pool.acquire(&anchor)?;
        assert!(std::ptr::eq(lease.file(), &anchor));
        assert_eq!(lease.file().as_raw_handle(), original);
        drop(lease);
        drop(pool);
        let mut output = [0; 4];
        read_exact_positioned(&anchor, 2, &mut output)?;
        assert_eq!(&output, b"2345");
        let _restore = RestoreEnvironment(std::env::var_os(ENV_NAME));
        unsafe { std::env::remove_var(ENV_NAME); }
        let default = RankReaderPool::from_env(&anchor)?;
        assert_eq!(default.count(), 1);
        assert!(std::ptr::eq(default.acquire(&anchor)?.file(), &anchor));
        unsafe { std::env::set_var(ENV_NAME, "2"); }
        let pair = RankReaderPool::from_env(&anchor)?;
        assert_eq!(pair.count(), 2);
        assert_ne!(pair.acquire(&anchor)?.file().as_raw_handle(), anchor.as_raw_handle());
        unsafe { std::env::set_var(ENV_NAME, " 2"); }
        match RankReaderPool::from_env(&anchor) {
            Err(error) => assert_eq!(error.kind(), ErrorKind::InvalidInput),
            Ok(_) => panic!("invalid environment was accepted"),
        }
        for count in [0, 65, usize::MAX] {
            match RankReaderPool::new(&anchor, count) {
                Err(error) => assert_eq!(error.kind(), ErrorKind::InvalidInput),
                Ok(_) => panic!("invalid count {count} was accepted"),
            }
        }
        let pool = RankReaderPool::new(&anchor, 64)?;
        let leases: Vec<_> = (0..64).map(|_| pool.acquire(&anchor)).collect::<io::Result<_>>()?;
        let mut handles: Vec<_> = leases.iter().map(|lease| lease.file().as_raw_handle() as usize).collect();
        handles.sort_unstable();
        handles.dedup();
        assert_eq!(handles.len(), 64);
        assert!(!handles.contains(&(anchor.as_raw_handle() as usize)));
        Ok(())
    }

    #[test]
    fn reopened_objects_have_independent_cursors_and_preserve_renamed_anchor_identity() -> io::Result<()> {
        // DuplicateHandle would share a file cursor and fail this consumer behavior.
        let _serial = FIXTURE_LOCK.lock().unwrap();
        let fixture = Fixture::new(b"original table")?;
        let mut anchor = fixture.anchor()?;
        anchor.seek(SeekFrom::Start(1))?;
        let pool = RankReaderPool::new(&anchor, 2)?;
        let first = pool.acquire(&anchor)?;
        let second = pool.acquire(&anchor)?;
        let mut a = first.file();
        let mut b = second.file();
        a.seek(SeekFrom::Start(2))?;
        b.seek(SeekFrom::Start(9))?;
        assert_eq!(a.stream_position()?, 2);
        assert_eq!(b.stream_position()?, 9);
        assert_eq!((&anchor).stream_position()?, 1);
        let mut left = [0; 2];
        let mut right = [0; 2];
        a.read_exact(&mut left)?;
        b.read_exact(&mut right)?;
        assert_eq!(&left, b"ig");
        assert_eq!(&right, b"ta");
        drop(first);
        drop(second);
        drop(pool);
        // Reopening the old pathname instead of the anchor would read replacement bytes.
        fs::rename(&fixture.path, fixture.directory.join("renamed.bin"))?;
        OpenOptions::new().write(true).create_new(true).open(&fixture.path)?.write_all(b"replacement!!!")?;
        let pool = RankReaderPool::new(&anchor, 2)?;
        let first = pool.acquire(&anchor)?;
        let second = pool.acquire(&anchor)?;
        for lease in [&first, &second] {
            let mut output = [0; 14];
            read_exact_positioned(lease.file(), 0, &mut output)?;
            assert_eq!(&output, b"original table");
        }
        assert_eq!(fs::read(&fixture.path)?, b"replacement!!!");
        Ok(())
    }

    #[test]
    fn concurrent_leased_ranges_remain_byte_exact_with_bounded_handles() -> io::Result<()> {
        let _serial = FIXTURE_LOCK.lock().unwrap();
        let bytes: Vec<_> = (0..65_536).map(|index| ((index * 17 + 9) % 251) as u8).collect();
        let fixture = Fixture::new(&bytes)?;
        let anchor = Arc::new(fixture.anchor()?);
        let pool = Arc::new(RankReaderPool::new(&anchor, 3)?);
        let held: Vec<_> = (0..3).map(|_| pool.acquire(&anchor)).collect::<io::Result<_>>()?;
        let allowed: Vec<_> = held.iter().map(|lease| lease.file().as_raw_handle() as usize).collect();
        assert_ne!(allowed[0], allowed[1]);
        assert_ne!(allowed[0], allowed[2]);
        assert_ne!(allowed[1], allowed[2]);
        drop(held);
        let allowed = Arc::new(allowed);
        let bytes = Arc::new(bytes);
        let start = Arc::new(Barrier::new(12));
        let active = Arc::new(AtomicUsize::new(0));
        let mut workers = Vec::new();
        for worker in 0..12 {
            let (pool, anchor, allowed, bytes, start, active) =
                (pool.clone(), anchor.clone(), allowed.clone(), bytes.clone(), start.clone(), active.clone());
            workers.push(std::thread::spawn(move || -> io::Result<()> {
                start.wait();
                for round in 0..40 {
                    let lease = pool.acquire(&anchor)?;
                    assert!(allowed.contains(&(lease.file().as_raw_handle() as usize)));
                    assert!(active.fetch_add(1, Ordering::SeqCst) + 1 <= 3);
                    let offset = (worker * 137 + round * 53) % (bytes.len() - 67);
                    std::thread::yield_now();
                    let mut output = [0; 67];
                    read_exact_positioned(lease.file(), offset as u64, &mut output)?;
                    assert_eq!(&output[..], &bytes[offset..offset + 67]);
                    active.fetch_sub(1, Ordering::SeqCst);
                }
                Ok(())
            }));
        }
        for worker in workers { worker.join().expect("reader worker panicked")?; }
        assert_eq!(active.load(Ordering::SeqCst), 0);
        Ok(())
    }

    #[test]
    fn eof_read_error_and_unwind_return_owned_readers_until_pool_drop_closes_them() -> io::Result<()> {
        let _serial = FIXTURE_LOCK.lock().unwrap();
        let fixture = Fixture::new(b"abcd")?;
        let anchor = fixture.anchor()?;
        let pool = RankReaderPool::new(&anchor, 2)?;
        let _held = pool.acquire(&anchor)?;
        let mut handle = 0usize;
        let result = (|| {
            let lease = pool.acquire(&anchor)?;
            handle = lease.file().as_raw_handle() as usize;
            read_exact_positioned(lease.file(), 3, &mut [0; 2])
        })();
        assert_eq!(result.unwrap_err().kind(), ErrorKind::UnexpectedEof);
        let returned = pool.acquire(&anchor)?;
        assert_eq!(returned.file().as_raw_handle() as usize, handle);
        let mut output = [0; 4];
        read_exact_positioned(returned.file(), 0, &mut output)?;
        assert_eq!(&output, b"abcd");
        drop(returned);
        let lock = FileLock::first_byte(&anchor)?;
        let mut handle = 0usize;
        let result = (|| {
            let lease = pool.acquire(&anchor)?;
            handle = lease.file().as_raw_handle() as usize;
            read_exact_positioned(lease.file(), 0, &mut [0; 1])
        })();
        assert_eq!(result.unwrap_err().raw_os_error(), Some(33)); // ERROR_LOCK_VIOLATION
        drop(lock);
        let returned = pool.acquire(&anchor)?;
        assert_eq!(returned.file().as_raw_handle() as usize, handle);
        let mut output = [0; 1];
        read_exact_positioned(returned.file(), 0, &mut output)?;
        assert_eq!(&output, b"a");
        drop(returned);
        let mut handle = 0usize;
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            let lease = pool.acquire(&anchor).unwrap();
            handle = lease.file().as_raw_handle() as usize;
            panic!("intentional lease-owner panic");
        }));
        assert!(result.is_err());
        let returned = pool.acquire(&anchor)?;
        assert_eq!(returned.file().as_raw_handle() as usize, handle);
        let mut output = [0; 4];
        read_exact_positioned(returned.file(), 0, &mut output)?;
        assert_eq!(&output, b"abcd");
        let handles = [_held.file().as_raw_handle() as usize, returned.file().as_raw_handle() as usize];
        for &handle in &handles { assert!(handle_is_open(handle)); }
        drop(returned);
        drop(_held);
        for &handle in &handles { assert!(handle_is_open(handle)); }
        drop(pool);
        // No new handles are opened between pool drop and these validity queries.
        for &handle in &handles { assert!(!handle_is_open(handle)); }
        assert!(handle_is_open(anchor.as_raw_handle() as usize));
        let mut output = [0; 4];
        read_exact_positioned(&anchor, 0, &mut output)?;
        assert_eq!(&output, b"abcd");
        Ok(())
    }
}
