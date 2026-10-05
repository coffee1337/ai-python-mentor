"""Bound API request bodies before validation; never log payloads or query strings."""
from starlette.responses import JSONResponse

class RequestSizeLimit:
    def __init__(self,app,limit=128*1024):
        self.app,self.limit=app,limit

    async def __call__(self,scope,receive,send):
        if scope['type']!='http':
            return await self.app(scope,receive,send)
        length=next((v for k,v in scope.get('headers',[]) if k==b'content-length'),None)
        try:
            if length is not None and not 0<=int(length)<=self.limit:
                return await JSONResponse({'detail':'Request body exceeds the limit'},status_code=413)(scope,receive,send)
        except ValueError:
            return await JSONResponse({'detail':'Invalid Content-Length'},status_code=400)(scope,receive,send)
        body=bytearray()
        while True:
            message=await receive()
            if message['type']=='http.disconnect':return
            body.extend(message.get('body',b''))
            if len(body)>self.limit:
                return await JSONResponse({'detail':'Request body exceeds the limit'},status_code=413)(scope,receive,send)
            if not message.get('more_body',False):break
        delivered=False
        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered=True
                return {'type':'http.request','body':bytes(body),'more_body':False}
            return await receive()
        return await self.app(scope,bounded_receive,send)
