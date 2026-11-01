"""The rewriter's second patch area for a text beyond the reach of a B (patch_nso.py SPLIT_MODE, split_plan), on synthetic stub lists, without game files."""
import ast
from pathlib import Path
import sys
import unittest

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import nso_asm

# patch_nso.py is a command-line program whose top level loads and rewrites an image: compile split_plan alone
tree = ast.parse((TOOLS / 'patch_nso.py').read_text())
L = 0x8000000 - 0x10000


def plan(marks, total, back_off):
    scope = {'NAME': 'main', 'BACK_OFF': back_off}
    exec(compile(ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'split_plan'], type_ignores=[]), str(TOOLS / 'patch_nso.py'), 'exec'), scope)
    return scope['split_plan'](marks, total)


def stubs(text_end, every, size):   # a stub of `size` bytes for a site every `every` bytes, in address order
    marks = [(a, i * size) for i, a in enumerate(range(0, text_end, every))]
    return marks, len(marks) * size


def reach(marks, total, back_off, split, front):
    """Independent check: the farthest distance of any site to its stub's first (front) or last (back) byte"""
    sizes = [(marks[i + 1][1] if i + 1 < len(marks) else total) - marks[i][1] for i in range(len(marks))]
    fp = bp = 0; far_front = far_back = 0
    for (a, _), n in zip(marks, sizes):
        if a < split: far_front = max(far_front, a - (-front + fp)); fp += n
        else: bp += n; far_back = max(far_back, back_off + bp - a)
    return far_front, far_back, fp


class SplitPlan(unittest.TestCase):
    def test_both_areas_reach(self):
        text_end = 0x8069090   # Demon Slayer 2 1.81: 128.4 MB
        marks, total = stubs(text_end, 1024, 128)
        back_off = 0xce00000
        split, front = plan(marks, total, back_off)
        ff, fb, fp = reach(marks, total, back_off, split, front)
        self.assertLessEqual(ff, L); self.assertLessEqual(fb, L)
        self.assertLessEqual(fp, front - 0x4000); self.assertEqual(front % 0x10000, 0)
        self.assertTrue(0 < split < text_end and split in {a for a, _ in marks})
        # in the middle of the range: both sides keep room
        self.assertGreater(L - ff, 0x100000); self.assertGreater(L - fb, 0x100000)

    def test_no_split_point(self):
        marks, total = stubs(0x8069090, 1024, 128)
        with self.assertRaises(AssertionError) as e: plan(marks, total, 0x20000000)   # the back area starts 512 MB from the code
        self.assertIn('no SPLIT point', str(e.exception))

    def test_dense_stubs(self):
        marks, total = stubs(0x8069090, 64, 96)   # 190 MB of stubs would never fit: the front stubs of the low half alone cannot reach
        with self.assertRaises(AssertionError): plan(marks, total, 0xce00000)


class CheckedBranch(unittest.TestCase):
    def test_reach_check_can_be_lifted(self):
        with self.assertRaises(AssertionError): nso_asm.B(0, 1 << 27)
        nso_asm.CHECK_REACH = False
        try: nso_asm.B(0, 1 << 27)
        finally: nso_asm.CHECK_REACH = True
        with self.assertRaises(AssertionError): nso_asm.B(0, 2)   # a misaligned target stays an error


if __name__ == '__main__':
    unittest.main()
