// nvn_host_write_texture (the movie decoders' native-texture output) takes RGBA bytes: into a BGRX8 / BGRA8 texture (sRGB too) the first and third byte of each texel trade places, so
// the sampled colour is the decoder's (DRAGON BALL Z: KAKAROT's BGRA8 movie texture came out with red and blue swapped); RGBA8, RGBX8_SRGB and the like keep the bytes as they are.
// The texel is read back from the texture's memory with nvn_deswizzle
#define nvn_game_fps nvn_game_fps_mtl_default
#include "../nvn/nvn_mtl.m"
#undef nvn_game_fps
#define g_ft g_ft_hle
#include "../nvn/hle_nvn.c"
#undef g_ft
uint64_t g_t0_ns;
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)

enum { W = 4, H = 4 };
// Writes a W x H picture of (200, 100, 50, 255) texels, row pitch `row` bytes (0 = tight), into a texture of `format`; the 4 bytes of texel (3, 2) read back are copied to got.
// Returns what nvn_host_write_texture returned
static int write_read(NVNformat format, size_t row, uint8_t got[4]) {
    const size_t len = 262144;
    uint8_t *mem = mmap(NULL, len, PROT_READ | PROT_WRITE, MAP_ANON | MAP_PRIVATE, -1, 0);
    if (mem == MAP_FAILED) abort();
    pool_t pool = {0}; pool_builder_t pb = {.mem = mem, .size = len, .flags = NVN_MEMORY_POOL_FLAGS_CPU_CACHED | NVN_MEMORY_POOL_FLAGS_GPU_CACHED};
    CHECK(h_nvnMemoryPoolInitialize((NVNmemoryPool *)&pool, (const NVNmemoryPoolBuilder *)&pb), "pool initialized");
    NVNtextureBuilder tb; NVNtexture tex = {0}; h_nvnTextureBuilderSetDefaults(&tb);
    h_nvnTextureBuilderSetWidth(&tb, W); h_nvnTextureBuilderSetHeight(&tb, H); h_nvnTextureBuilderSetFormat(&tb, format);
    h_nvnTextureBuilderSetStorage(&tb, (NVNmemoryPool *)&pool, 65536);
    CHECK(h_nvnTextureInitialize(&tex, &tb), "texture initialized");
    size_t pitch = row ? row : W * 4;
    uint8_t *src = calloc(pitch * H, 1);
    for (int y = 0; y < H; y++) for (int x = 0; x < W; x++) { uint8_t *p = src + y * pitch + x * 4; p[0] = 200; p[1] = 100; p[2] = 50; p[3] = 255; }
    int tw = 0, th = 0, f = nvn_host_write_texture(&tex, src, W, H, row, &tw, &th);
    CHECK(tw == W && th == H, "texture size reported");
    uint8_t lin[W * H * 4]; memset(lin, 0, sizeof lin);
    tex_t *t = (tex_t *)&tex;
    CHECK(!nvn_deswizzle(&t->d, 0, 0, t->mem, lin, W * 4), "texture read back");
    memcpy(got, lin + (2 * W + 3) * 4, 4);
    h_nvnTextureFinalize(&tex); h_nvnMemoryPoolFinalize((NVNmemoryPool *)&pool);
    free(src); defer_drain(); munmap(mem, len);
    return f;
}
static void expect(NVNformat format, size_t row, int swapped, const char *label) {
    uint8_t g[4] = {0}; int f = write_read(format, row, g);
    static const uint8_t keep[4] = {200, 100, 50, 255}, swap[4] = {50, 100, 200, 255};
    char msg[160];
    snprintf(msg, sizeof msg, "%s: returns the format", label); CHECK(f == (int)format, msg);
    snprintf(msg, sizeof msg, "%s: bytes %u,%u,%u,%u", label, g[0], g[1], g[2], g[3]); CHECK(!memcmp(g, swapped ? swap : keep, 4), msg);
}
int main(void) { @autoreleasepool {
    expect(NVN_FORMAT_BGRA8, 0, 1, "BGRA8");
    expect(NVN_FORMAT_BGRA8, 64, 1, "BGRA8, row pitch 64");
    expect(NVN_FORMAT_BGRX8, 0, 1, "BGRX8");
    expect(NVN_FORMAT_BGRA8_SRGB, 0, 1, "BGRA8_SRGB");
    expect(NVN_FORMAT_BGRX8_SRGB, 0, 1, "BGRX8_SRGB");
    expect(NVN_FORMAT_RGBA8, 0, 0, "RGBA8");
    expect(NVN_FORMAT_RGBA8, 64, 0, "RGBA8, row pitch 64");
    expect(NVN_FORMAT_RGBX8_SRGB, 0, 0, "RGBX8_SRGB");
    int dummy[16] = {0};
    CHECK(nvn_host_write_texture(dummy, NULL, 0, 0, 0, NULL, NULL) == -1, "a non-texture returns -1");
    printf("t_movie_bgra: %d checks, %d failed\n", checks, failed);
    return failed ? 1 : 0;
} }
