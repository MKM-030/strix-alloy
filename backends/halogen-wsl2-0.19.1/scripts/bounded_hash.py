"""Read-only checksum with bounded buffers and per-range cache reclamation."""
import hashlib,json,os,sys

def file_identity(s):
    return dict(size=s.st_size,device=s.st_dev,inode=s.st_ino,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns)

def hash_file(path, chunk_bytes=8*1024**2):
    if not 4096<=chunk_bytes<=64*1024**2 or chunk_bytes%4096:
        raise ValueError('Chunk size must be page aligned and 4KiB..64MiB')
    digest=hashlib.sha256(); position=0
    with open(path,'rb',buffering=0) as stream:
        before=file_identity(os.fstat(stream.fileno()))
        while True:
            block=stream.read(chunk_bytes)
            if not block: break
            digest.update(block)
            if hasattr(os,'posix_fadvise'):
                # Only the checksum reader's consumed range; no global cache drop.
                os.posix_fadvise(stream.fileno(),position,len(block),os.POSIX_FADV_DONTNEED)
            position+=len(block)
        after=file_identity(os.fstat(stream.fileno()))
        if after!=before or position!=before['size']:
            raise ValueError('Checkpoint changed during checksum verification')
    return dict(sha256=digest.hexdigest(),identity=after,read_mode='bounded-cache',chunk_bytes=chunk_bytes)

if __name__=='__main__':print(json.dumps(hash_file(sys.argv[1])))
