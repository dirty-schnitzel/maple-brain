import sys, struct, zlib, os
exe, out = sys.argv[1], sys.argv[2]
data = open(exe, 'rb').read()
sig = bytes.fromhex('8b1202b96a61203872 7b9302 14d7a032 13f5b9e6 efae3318 ee3b2dce 24b36aae'.replace(' ', ''))
i = data.find(sig); assert i > 0
hdr = struct.unpack_from('<q', data, i - 8)[0]
p = hdr
def rd(fmt):
    global p
    v = struct.unpack_from(fmt, data, p); p += struct.calcsize(fmt); return v[0]
def rstr():
    global p
    n = 0; sh = 0
    while True:
        b = data[p]; p += 1; n |= (b & 0x7f) << sh; sh += 7
        if b < 0x80: break
    s = data[p:p+n].decode(); p += n; return s
major, minor, count = rd('<I'), rd('<I'), rd('<i'); bid = rstr()
if major >= 2: p += 8*4 + 8
print('bundle v', major, minor, count, 'files')
for _ in range(count):
    off, size = rd('<q'), rd('<q'); csize = rd('<q') if major >= 6 else 0
    typ = rd('<B'); path = rstr()
    blob = data[off:off + (csize or size)]
    if csize: blob = zlib.decompress(blob, -15)
    dst = os.path.join(out, path); os.makedirs(os.path.dirname(dst) or out, exist_ok=True)
    open(dst, 'wb').write(blob)
