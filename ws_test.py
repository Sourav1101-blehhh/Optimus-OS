import asyncio
import json

async def test():
    try:
        import websockets
        print('Connecting...')
        async with websockets.connect('ws://127.0.0.1:8000/ws') as ws:
            print('CONNECTED')
            auth_payload = {
        "password": "CHANGE_ME_IN_PRODUCTION"
    }        
            await ws.send(json.dumps(auth_payload))
            for _ in range(3):
                msg = await asyncio.wait_for(ws.recv(), timeout=3)
                d = json.loads(msg)
                print('  recv type:', d.get('type'))

            await ws.send(json.dumps({'command': 'THINK', 'text': 'what is my cpu usage?', 'engine': 'GEMINI'}))
            print('SENT command')

            for _ in range(15):
                msg = await asyncio.wait_for(ws.recv(), timeout=10)
                if msg.startswith('{'):
                    d = json.loads(msg)
                    t = d.get('type')
                    print('  JSON:', t)
                    if t == 'stream_end':
                        print('SUCCESS - full pipeline working')
                        break
                else:
                    print('  token:', repr(msg[:50]))
    except Exception as e:
        print('FAILED:', type(e).__name__, str(e))

asyncio.run(test())
