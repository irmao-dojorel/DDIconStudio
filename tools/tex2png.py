import io, struct, sys
from PIL import Image

def tex_to_png(src, dst):
    b = open(src, "rb").read()
    w, h = struct.unpack_from("<HH", b, 8)
    fmt = struct.unpack_from("<I", b, 16)[0]
    data = b[56:]
    # DDS + DX10 (BC7_UNORM_SRGB=99)
    hdr = b"DDS " + struct.pack("<7I", 124, 0x1007 | 0x80000, h, w, len(data), 0, 1)
    hdr += b"\0" * 44
    hdr += struct.pack("<II4s5I", 32, 4, b"DX10", 0, 0, 0, 0, 0)
    hdr += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    hdr += struct.pack("<5I", 99, 3, 0, 1, 0)
    im = Image.open(io.BytesIO(hdr + data)).convert("RGBA")
    im.save(dst)
    print(src, w, h, hex(fmt), im.size)

if __name__ == "__main__":
    tex_to_png(sys.argv[1], sys.argv[2])
