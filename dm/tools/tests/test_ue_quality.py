"""Unreal graphics-quality presets (dm/tools/ue_quality.py): uepak.write_pak's pak read back by uepak.Pak, and the ini editor on a CRLF fixture."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'dm/gfx/tools'))
import uepak
spec = importlib.util.spec_from_file_location('ue_quality', ROOT / 'dm/tools/ue_quality.py')
uq = importlib.util.module_from_spec(spec)
spec.loader.exec_module(uq)

INI = ('[Other DeviceProfile]\r\n+CVars=r.setres=1\r\n\r\n'
       '[SwitchConsole DeviceProfile]\r\nDeviceType=Switch\r\n+CVars=r.setres=1600x900\r\n+CVars=r.MaxAnisotropy=1\r\n\r\n'
       '[Switch DeviceProfile]\r\n+TextureLODGroups=(Group=TEXTUREGROUP_World,MinLODSize=1,MinMagFilter=linear,MipFilter=point,MipGenSettings=TMGS_SimpleAverage)\r\n'
       '+TextureLODGroups=(Group=TEXTUREGROUP_UI,MinMagFilter=linear,MipFilter=point)\r\n')


class WritePakTests(unittest.TestCase):
    def test_round_trip(self):
        files = [('A/B/one.ini', b'x=1\r\n'), ('A/two.bin', bytes(range(256)) * 9), ('top.txt', b''), ('A/B/C/three', b'3')]
        with tempfile.TemporaryDirectory() as d:
            f = str(Path(d) / 'p_99_P.pak'); uepak.write_pak(f, '../../../', files)
            p = uepak.Pak(f)
            self.assertEqual(p.mount, '../../../')
            self.assertEqual(sorted(p.files), sorted(n for n, _ in files))
            for n, b in files: self.assertEqual(p.read(n), b, n)


class IniEditTests(unittest.TestCase):
    def test_replace_add_and_line_ends(self):
        t = uq.apply(INI, 'SwitchConsole DeviceProfile', [('r.setres', '1920x1080'), ('r.Shadow.MaxResolution', '1024')])
        self.assertIn('[SwitchConsole DeviceProfile]\r\nDeviceType=Switch\r\n+CVars=r.setres=1920x1080\r\n+CVars=r.MaxAnisotropy=1\r\n+CVars=r.Shadow.MaxResolution=1024\r\n\r\n[Switch', t)
        self.assertIn('[Other DeviceProfile]\r\n+CVars=r.setres=1\r\n', t)   # other sections untouched
        self.assertNotIn('\n', t.replace('\r\n', ''))

    def test_texture_lod_groups(self):
        t = uq.apply(INI, 'Switch DeviceProfile', [('TextureLODGroups', 'MinMagFilter=aniso,MipFilter=linear')])
        self.assertIn('MinLODSize=1,MinMagFilter=aniso,MipFilter=linear,MipGenSettings=TMGS_SimpleAverage)\r\n', t)
        self.assertIn('+TextureLODGroups=(Group=TEXTUREGROUP_UI,MinMagFilter=aniso,MipFilter=linear)\r\n', t)

    def test_guarded_field(self):
        ini = INI.replace('MinMagFilter=linear,MipFilter=point)', 'MinMagFilter=point,MipFilter=linear)')
        t = uq.apply(ini, 'Switch DeviceProfile', [('TextureLODGroups', 'MinMagFilter=linear>aniso,MipFilter=point>linear')])
        self.assertIn('MinMagFilter=aniso,MipFilter=linear,MipGenSettings', t)
        self.assertIn('+TextureLODGroups=(Group=TEXTUREGROUP_UI,MinMagFilter=point,MipFilter=linear)', t)

    def test_errors(self):
        with self.assertRaisesRegex(uq.Error, 'no section'): uq.apply(INI, 'Missing DeviceProfile', [('r.x', '1')])
        with self.assertRaisesRegex(uq.Error, 'no \\+TextureLODGroups'): uq.apply(INI, 'SwitchConsole DeviceProfile', [('TextureLODGroups', 'MipFilter=linear')])

    def test_profile_table(self):
        rows = uq.rows(ROOT / 'dm/games/0100AD80208A8000/ue_quality.tsv')
        self.assertEqual({r[0] for r in rows}, {'high', 'veryhigh', 'max'})
        self.assertEqual({r[1] for r in rows}, {'APK2/Platforms/Switch/Config/SwitchDeviceProfiles.ini'})


class PlainKey(unittest.TestCase):
    INI = '[/Script/Engine.Engine]\r\nbUseFixedFrameRate=True\r\nFixedFrameRate=30.000000\r\n[Other]\r\nFixedFrameRate=30.000000\r\n'
    def test_replaced_in_its_section(self):
        out = uq.apply(self.INI, '/Script/Engine.Engine', [('=FixedFrameRate', '60.000000')])
        self.assertEqual(out, self.INI.replace('FixedFrameRate=30.000000', 'FixedFrameRate=60.000000', 1))
    def test_missing_line_stops(self):
        with self.assertRaises(uq.Error): uq.apply(self.INI, 'Other', [('=bUseFixedFrameRate', 'False')])

if __name__ == '__main__': unittest.main()
