// Tegra X1 block-linear layout, one mip level at a time, for dm/tools/ue_pc_paks.py: dst[] (gob_cols * block rows * 2^th GOBs of 512 bytes) from src[], rows linear rows of row_bytes bytes.
// A GOB is 64 bytes x 8 rows; byte x and row y sit at bits x0-3, y0, x4, y1, y2, x5 of its 512 bytes. Blocks of 2^th GOBs stack the GOBs vertically, block rows go left to right in gob_cols columns.
// The same layout as dm/gfx/nvn/nvn_tex.c's level_walk: that file sizes and places levels for the host, this one moves bytes for a tool that runs without the host.
#include <stdint.h>
#include <string.h>
static inline uint32_t gob_off(uint32_t x, uint32_t y) {
    return (x & 15) | (y & 1) << 4 | (x >> 4 & 1) << 5 | (y >> 1 & 1) << 6 | (y >> 2 & 1) << 7 | (x >> 5 & 1) << 8;
}
void bl_swizzle(const uint8_t *src, uint8_t *dst, uint32_t row_bytes, uint32_t rows, uint32_t gob_cols, uint32_t th) {
    uint32_t bh = 8u << th;                    // rows of a block of GOBs
    for (uint32_t y = 0; y < rows; y++) {
        const uint8_t *s = src + (uint64_t)y * row_bytes;
        uint64_t base = (uint64_t)(y / bh) * gob_cols << (9 + th);
        uint32_t gy = (y % bh) >> 3, sub = y & 7;
        for (uint32_t x = 0; x < row_bytes; x += 16) {   // bits 0-3 of the offset are x's: 16 bytes stay together
            uint32_t n = row_bytes - x < 16 ? row_bytes - x : 16;
            uint64_t o = base + ((uint64_t)(x >> 6) << (9 + th)) + ((uint64_t)gy << 9) + gob_off(x & 63, sub);
            memcpy(dst + o, s + x, n);
        }
    }
}
