// A texture on the storage of another with the same description but more mip levels is a view of its first levels (Naruto STORM 4 copies into a 2-level texture and samples a 1-level one on the same storage).
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t g_mod[MAX_MOD]; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, failed;
#define CHECK(c, label) do { checks++; if (!(c)) { failed++; fprintf(stderr, "FAIL: %s\n", label); } } while (0)
int main(void) { @autoreleasepool {
    mtl_init(); mtl_sub_begin();
    tex_t a = {.magic=MAGIC('T','E','X',0), .serial=99501, .off=0x10000};
    a.d = (nvn_texdesc){.target=NVN_TEXTURE_TARGET_2D, .format=NVN_FORMAT_RGBA8, .width=4, .height=4, .depth=1, .levels=2, .samples=1};
    nvn_tex_layout(&a.d, &a.L);
    tex_t b = a; b.serial++; b.d.levels = 1; nvn_tex_layout(&b.d, &b.L);
    tex_t c = b; c.serial++; c.off = 0x20000;
    tex_t f = b; f.serial++; f.d.format = NVN_FORMAT_R32F; nvn_tex_layout(&f.d, &f.L);
    mtl_tex_init(&a); mtl_tex_init(&b); mtl_tex_init(&c); mtl_tex_init(&f);
    id<MTLTexture> ta = tex_mtl(&a), tb = tex_mtl(&b), tc = tex_mtl(&c), tf = tex_mtl(&f);
    CHECK(ta && ta.mipmapLevelCount == 2 && !ta.parentTexture, "the 2-level texture has an image of its own");
    CHECK(tb && tb.parentTexture == ta && tb.mipmapLevelCount == 1, "the 1-level texture on its storage is a view of its first level");
    CHECK(tc && !tc.parentTexture && tc != ta, "a 1-level texture on other storage has an image of its own");
    CHECK(tf && tf.parentTexture != ta, "a texture of another format on the same storage is no view of it");
    CHECK(tex_mtl(&b) == tb, "the view is resolved again by its serial");
    CHECK(g_view_bases && CFSetContainsValue(g_view_bases, (__bridge const void *)ta), "the base is marked as viewed");
    uint32_t pixels[16]; for (int i = 0; i < 16; i++) pixels[i] = 0x44332211u + (uint32_t)i;
    id<MTLBuffer> src = [g_dev newBufferWithBytes:pixels length:sizeof pixels options:MTLResourceStorageModeShared]; res_add(src);
    id<MTL4ComputeCommandEncoder> encoder = blit();
    enc_b_copy_buffer_texture(encoder, src, 0, 16, sizeof pixels, MTLSizeMake(4,4,1), ta, 0, 0, MTLOriginMake(0,0,0));
    id<MTLBuffer> dst = [g_dev newBufferWithLength:sizeof pixels options:MTLResourceStorageModeShared]; res_add(dst);
    encoder = blit(); enc_b_copy_texture_buffer(encoder, tb, 0, 0, MTLOriginMake(0,0,0), MTLSizeMake(4,4,1), dst, 0, 16, sizeof pixels);
    mtl_sub_commit(); mtl_drain();
    CHECK(!memcmp(dst.contents, pixels, sizeof pixels), "the view reads what the GPU copied into the base");
    printf("texture mip-prefix aliases: %d checks, %d failed\n", checks, failed);
    return failed != 0;
} }
