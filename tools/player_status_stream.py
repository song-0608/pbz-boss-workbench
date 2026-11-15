"""Incremental bounded HUD log reader; no process access, input or game calls."""
import json
import math


def valid_status(value,session,now):
    def number(item):return type(item)in(int,float)and math.isfinite(item)
    return (isinstance(value,dict)and value.get('session')==session
        and number(value.get('at'))and 0<=now-value['at']<=3
        and number(value.get('expires_at'))and now<value['expires_at']
        and isinstance(value.get('text'),str)and len(value['text'])<=4096
        and isinstance(value.get('player'),str))


class StatusStream:
    def __init__(self,path,session,tail_existing=True):
        self.path=path;self.session=session;self.position=None;self.pending=b'';self.latest=None
        self.bytes_read=0;self.identity=None;self.tail_existing=tail_existing

    def read(self,now):
        try:info=self.path.stat()
        except FileNotFoundError:
            self.position=None;self.pending=b'';self.latest=None;self.identity=None;return None
        size=info.st_size;identity=(info.st_dev,info.st_ino)
        if self.position is None or size<self.position or identity!=self.identity:
            self.position=max(0,size-65536)if self.tail_existing or self.identity is not None else size
            self.pending=b'';self.latest=None
            self.identity=identity
        if size-self.position>262144:
            self.position=max(0,size-65536);self.pending=b'';self.latest=None
        raw=b''
        if size>self.position:
            with self.path.open('rb')as stream:
                stream.seek(self.position);raw=stream.read(262144);self.position=stream.tell()
        self.bytes_read+=len(raw)
        parts=(self.pending+raw).split(b'\n');self.pending=parts.pop()[-16384:]
        for line in parts:
            marker=b'PBZ_PLAYER_UI:STATUS='
            offset=line.find(marker)
            if offset<0:continue
            try:value=json.loads(line[offset+len(marker):].decode('utf-8'))
            except (ValueError,UnicodeError):continue
            # A foreign-session line cannot replace an owned latest status.
            if valid_status(value,self.session,now):self.latest=value
        return self.latest if valid_status(self.latest,self.session,now)else None
