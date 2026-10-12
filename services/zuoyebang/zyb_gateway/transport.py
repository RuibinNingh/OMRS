"""有总读取期限、字节上限的官方 HTTP 响应读取器。"""
import time

class ResponseBudget(ValueError):
    pass


def bounded_read(response,limit,deadline):
    length=response.headers.get('Content-Length')
    if length is not None and (not length.isdigit() or int(length)>limit):
        raise ResponseBudget('官方响应超出字节预算')
    chunks=[];total=0
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:raise TimeoutError('官方响应读取超过总期限')
        # urllib 返回的 HTTPResponse 保留原 socket；每次实际网络读都收紧剩余期限。
        stream=getattr(response,'fp',None)
        raw=getattr(stream,'raw',None)
        sock=getattr(raw,'_sock',None)
        if sock is not None:sock.settimeout(remaining)
        read=getattr(response,'read1',response.read)
        chunk=read(min(65536,limit-total+1))
        if not chunk:break
        total+=len(chunk)
        if total>limit:raise ResponseBudget('官方响应超出字节预算')
        chunks.append(chunk)
    return b''.join(chunks)
