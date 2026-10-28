"""Cap VPN response decryptor.
Format: base64( IV[16] + "::" + base64(AES-CBC-PKCS5(raw_json)) )
AES key: ChangeThisToA32CharRandomString!  (32 bytes ASCII)
"""
import base64, sys, json
from Crypto.Cipher import AES

KEY = b"ChangeThisToA32CharRandomString!"
assert len(KEY) == 32

def decrypt(raw: bytes) -> bytes:
    raw = raw.strip()
    d = base64.b64decode(raw)
    i = d.find(b"::")
    if i < 0:
        raise ValueError("delimiter '::' not found")
    iv = d[:16]
    if i != 16:
        print(f"[warn] delimiter at {i}, iv={iv.hex()}", file=sys.stderr)
    ct = base64.b64decode(d[i + 2:])
    c = AES.new(KEY, AES.MODE_CBC, iv)
    return c.decrypt(ct)[:-ct[-1]] if False else _unpad(c.decrypt(ct))

def _unpad(b: bytes) -> bytes:
    p = b[-1]
    if 1 <= p <= 16 and b.endswith(bytes([p]) * p):
        return b[:-p]
    return b

if __name__ == "__main__":
    data = open(sys.argv[1], "rb").read()
    out = decrypt(data)
    try:
        print(json.dumps(json.loads(out), ensure_ascii=False, indent=2))
    except Exception:
        sys.stdout.buffer.write(out)
