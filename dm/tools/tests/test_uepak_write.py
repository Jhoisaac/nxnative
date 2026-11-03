"""uepak.write_pak: a replacement pak of each written version reads back through uepak.Pak, with the footer an engine of that version expects"""
import os, struct, sys, tempfile, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '../../gfx/tools'))
import uepak

FILES = [('HeroGame/Config/DefaultDeviceProfiles.ini', b'[Switch DeviceProfile]\r\n+CVars=r.setres=3840x2160\r\n'), ('Engine/Config/Base.ini', b''), ('a.ini', b'x' * 70000)]

class WritePak(unittest.TestCase):
    def roundtrip(self, version):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'x_99_P.pak'); uepak.write_pak(p, '../../../', FILES, version)
            pak = uepak.Pak(p)
            self.assertEqual((pak.version, pak.mount), (version, '../../../'))
            self.assertEqual(set(pak.files), {n for n, _ in FILES})
            for n, b in FILES: self.assertEqual(pak.read(n), b)
            with open(p, 'rb') as f: self.assertFalse(uepak.frozen_index(f))

    def test_each_version(self):
        for v in (4, 7, 8, 9, 11):
            with self.subTest(version=v): self.roundtrip(v)

    def test_legacy_footer_sizes(self):
        for v, back in ((4, 0x2c), (7, 0x2c), (8, 0xcc), (9, 0xcd)):
            with tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, 'x.pak'); uepak.write_pak(p, '../../../', FILES, v)
                with open(p, 'rb') as f:
                    self.assertEqual(uepak.magic_back(f), (back, v))
                    f.seek(-(back - 8), 2); ioff, isz = struct.unpack('<QQ', f.read(16))
                    f.seek(ioff); self.assertEqual(struct.unpack('<i', f.read(4))[0], len('../../../') + 1)

    def test_zlib_blocks(self):
        import zlib
        raw = bytes(range(256)) * 700   # 179,200 bytes: three blocks of 64 KB
        chunks = [zlib.compress(raw[i:i + 65536]) for i in range(0, len(raw), 65536)]
        for v in (4, 7, 8, 9):
            with self.subTest(version=v), tempfile.TemporaryDirectory() as d:
                p = os.path.join(d, 'x.pak')
                with uepak.LegacyPakWriter(p, '../../../', v) as w:
                    w.add('a.ini', b'stored'); w.add_zlib('b/t.ubulk', chunks, len(raw), 65536); w.add('c.ini', b'after')
                pak = uepak.Pak(p)
                self.assertEqual(pak.read('b/t.ubulk'), raw); self.assertEqual(pak.read('a.ini'), b'stored'); self.assertEqual(pak.read('c.ini'), b'after')
                self.assertEqual(pak.files['b/t.ubulk']['method'], 'Zlib')

    def test_version_12_refused(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(ValueError):
            uepak.write_pak(os.path.join(d, 'x.pak'), '../../../', FILES, 12)

if __name__ == '__main__': unittest.main()
