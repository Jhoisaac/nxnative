// Vertex attribute conversion on the GPU (vconv_bind's helper draw) against the CPU's (vconv_fill): every format the conversion handles, as the draw's own vertex stage reads it.
// Each format is drawn through the replay (rasterizer discard, a vertex function that stores its attribute as 32-bit words in a storage buffer) with its stream at an odd stride and
// attribute offset, so the elements are unaligned; the stored words must equal vconv_fill's bytes. DM_VCONV_GPU=0 runs the same draws on the CPU path (the Makefile runs both).
#include "../nvn/nvn_mtl.m"
void *front_metal_layer(void) { return NULL; }
module_t *module_of(const void *p) { (void)p; return NULL; }
module_t *g_mod; int g_nmod;
void svc_thread_dump(void) {}
uint64_t now_ns(void) { return bp_now(); }
static int checks, fails;
#define CHECK(c, label) do { checks++; if (!(c)) { fails++; fprintf(stderr,"FAIL: %s\n",label); } } while (0)
enum { NV = 300, MAXF = 128, ROUNDS = 3 };
static uint8_t *cmd; static size_t used;
static void emit(unsigned op, const void *p, size_t n) {
    size_t z = (8 + n + 7) & ~7ull; op_hdr h = {op, (uint32_t)z};
    memcpy(cmd + used, &h, 8); if (n) memcpy(cmd + used + 8, p, n); used += z;
}
static void execute(void) {
    emit(OP_END,NULL,0); mtl_sub_begin(); uint64_t handle=(uint64_t)cmd; mtl_sub_index(&handle,1); mtl_exec(cmd);
    uint64_t fence=mtl_sub_commit(); CHECK(mtl_wait(fence,5000000000ull),"GPU submission completes");
    CHECK(!mtl_last_commit_error(),"GPU reports no error"); used=0;
}
static uint32_t rng = 12345;
static uint32_t rnd(void) { rng = rng * 1664525u + 1013904223u; return rng >> 8; }
// Which formats the conversion handles, as vconv_wanted sees them: the shader input type that makes it take each one
typedef struct { int f, ct; } job;
int main(void) { @autoreleasepool {
    setenv("DM_NVN_TBDR","0",1); setenv("DM_NVN_VCONV_RANGE","1",1); mtl_init();
    int gpu_on = !(getenv("DM_VCONV_GPU") && !strcmp(getenv("DM_VCONV_GPU"), "0"));
    size_t psz = 4 << 20; void *memory = NULL; if (posix_memalign(&memory, getpagesize(), psz)) abort(); memset(memory, 0, psz); mtl_pool_add(memory, psz);
    cmd = memory; uint8_t *vdata = (uint8_t *)memory + 65536; uint32_t *out = (uint32_t *)((uint8_t *)memory + (2 << 20));   // out: one NV x 4 words block per job
    NSError *error = nil; id<MTLLibrary> lib = [g_dev newLibraryWithSource:@"#include <metal_stdlib>\nusing namespace metal;\n"
        "struct A { device uint *p [[id(0)]]; };\n"
        "struct IF { float4 a [[attribute(0)]]; }; struct IU { uint4 a [[attribute(0)]]; }; struct II { int4 a [[attribute(0)]]; };\n"
        "vertex void df(IF i [[stage_in]], uint n [[vertex_id]], constant A &a [[buffer(0)]]) { a.p[n*4]=as_type<uint>(i.a.x); a.p[n*4+1]=as_type<uint>(i.a.y); a.p[n*4+2]=as_type<uint>(i.a.z); a.p[n*4+3]=as_type<uint>(i.a.w); }\n"
        "vertex void du(IU i [[stage_in]], uint n [[vertex_id]], constant A &a [[buffer(0)]]) { a.p[n*4]=i.a.x; a.p[n*4+1]=i.a.y; a.p[n*4+2]=i.a.z; a.p[n*4+3]=i.a.w; }\n"
        "vertex void di(II i [[stage_in]], uint n [[vertex_id]], constant A &a [[buffer(0)]]) { a.p[n*4]=uint(i.a.x); a.p[n*4+1]=uint(i.a.y); a.p[n*4+2]=uint(i.a.z); a.p[n*4+3]=uint(i.a.w); }\n"
        "vertex float4 vv(uint n [[vertex_id]]) { return float4(0,0,0,1); }\n"
        "fragment float4 f() { return float4(1,0,0,1); }\n" options:nil error:&error];
    if (!lib) { fprintf(stderr, "%s\n", error.localizedDescription.UTF8String); return 1; }
    static prog_t pg[3] = {{.serial=920501},{.serial=920502},{.serial=920503}}; NvProg *prog[3]; const char *dn[3] = {"df","du","di"}; int cts[3] = {NVN_CT_FLOAT, NVN_CT_UINT, NVN_CT_INT};
    for (int k = 0; k < 3; k++) {
        prog[k] = [NvProg new]; NvShader *vs = [NvShader new]; vs->fn = [lib newFunctionWithName:@"vv"]; vs->discard_fn = [lib newFunctionWithName:@(dn[k])]; vs->ae = [vs->discard_fn newArgumentEncoderWithBufferIndex:0];
        vs->rf.nb = 1; vs->rf.b[0] = (nvn_rbind){.kind=NVN_RB_SBUFP,.rw=1,.reg=0,.aid=0}; vs->rf.nv = 1; vs->rf.v[0].ct = cts[k]; vs->rf.v[0].nvn = 0; vs->rf.v[0].loc = 0; memset(vs->rf.v[0].sh, 0xff, sizeof vs->rf.v[0].sh);
        prog[k]->sh[0] = vs; prog[k]->sh[1] = [NvShader new]; prog[k]->sh[1]->fn = [lib newFunctionWithName:@"f"]; prog[k]->sh[1]->stage = 1; serial_put(pg[k].serial, prog[k]); }
    tex_t t = {.magic=MAGIC('T','E','X',0),.serial=920510}; t.d = (nvn_texdesc){.target=NVN_TEXTURE_TARGET_2D,.format=NVN_FORMAT_RGBA8,.width=8,.height=8,.depth=1,.levels=1,.samples=1};
    // The formats: float-type ones feed a uint input; 8 / 16-bit integers a float input and one of the other sign; integers read as floats a float and a uint input
    job jobs[MAXF]; int nj = 0;
    for (int f = 0; f < 0xA0; f++) {
        int ib, is;
        if (vconv_ncomp(f)) jobs[nj++] = (job){f, NVN_CT_UINT};
        else if (vconv_int(f, &ib, &is)) { jobs[nj++] = (job){f, NVN_CT_FLOAT}; jobs[nj++] = (job){f, is ? NVN_CT_UINT : NVN_CT_INT}; }
        else if (vconv_i2f(f, &ib, &is)) { jobs[nj++] = (job){f, NVN_CT_FLOAT}; jobs[nj++] = (job){f, NVN_CT_UINT}; }
    }
    CHECK(nj > 80 && nj < MAXF, "the format list is the expected size");
    int nfmt = 0, last = -1; for (int i = 0; i < nj; i++) if (jobs[i].f != last) { nfmt++; last = jobs[i].f; }
    uint64_t runs0 = g_vcg_runs;
    for (int round = 0; round < ROUNDS; round++) {
        // Source data: random bytes; the first elements all zero, all 0xff, all 0x80 and all 0x7f. Half floats avoid NaN encodings (their payload is not part of what is compared)
        uint32_t stride[MAXF], off = 1; uint8_t *src = vdata;
        state_reset(); memset(&R, 0, sizeof R);
        p_set_rt rt = {.n=1}; rt.color[0] = &t; emit(OP_SET_RT, &rt, sizeof rt);
        p_rast_discard rd = {.on=1}; emit(OP_RAST_DISCARD, &rd, sizeof rd);
        ds_st ds = {.df=NVN_DEPTH_FUNC_ALWAYS}; p_bind_state bs = {.kind=5}; memcpy(bs.bytes, &ds, sizeof ds); emit(OP_BIND_STATE, &bs, sizeof bs);
        static float expect[MAXF][NV * 4];
        for (int i = 0; i < nj; i++) {
            int f = jobs[i].f, es = vconv_size(f); stride[i] = (uint32_t)es + 5;
            size_t span = off + (size_t)NV * stride[i];
            for (size_t b = 0; b < span; b++) src[b] = (uint8_t)rnd();
            for (int v = 0; v < 4; v++) memset(src + off + (size_t)v * stride[i], v == 0 ? 0 : v == 1 ? 0xff : v == 2 ? 0x80 : 0x7f, es);
            if (f == 0x05 || f == 0x11 || f == 0x1D || f == 0x29) for (int v = 0; v < NV; v++) for (int c = 0; c < vconv_ncomp(f); c++) {
                uint8_t *h = src + off + (size_t)v * stride[i] + 2 * c; if ((h[1] & 0x7c) == 0x7c) h[1] &= 0xbf; }   // exponent 31 -> 30
            vconv_fill(f, (uint64_t)(uintptr_t)(src + off), stride[i], NV, expect[i]);
            // one stream of its own per job: the data, a stride, the attribute
            va_st va = {.fmt = (uint32_t)f, .offset = off, .stream = 0}; p_bind_vattr ba = {.first = 0, .n = 1}; memcpy(&ba.st[0], &va, 4); emit(OP_BIND_VATTR, &ba, sizeof ba);
            p_bind_vstream bt = {.first = 0, .n = 1}; bt.st[0] = (vs_st){stride[i], 0}; emit(OP_BIND_VSTREAM, &bt, sizeof bt);
            p_bind_vbuf bv = {.first = 0, .n = 1}; bv.r[0] = (NVNbufferRange){(uint64_t)(uintptr_t)src, span}; emit(OP_BIND_VBUF, &bv, sizeof bv);
            int k = jobs[i].ct == NVN_CT_FLOAT ? 0 : jobs[i].ct == NVN_CT_UINT ? 1 : 2; p_bind_program bp = {.prog=&pg[k],.stages=3}; emit(OP_BIND_PROGRAM, &bp, sizeof bp);
            p_bind_buf buf = {.stage=0,.index=0,.addr=(uint64_t)(uintptr_t)(out + (size_t)i * NV * 4),.size=NV * 16}; emit(OP_BIND_SSBO, &buf, sizeof buf);
            p_draw dw = {.prim=NVN_DRAW_PRIMITIVE_POINTS,.first=0,.count=NV,.instances=1}; emit(OP_DRAW, &dw, sizeof dw);
            src += (span + 255) & ~255ull;   // the next job's data
        }
        memset(out, 0xEE, (size_t)nj * NV * 16);
        execute();
        int bad = 0; for (int i = 0; i < nj; i++) {
            const uint32_t *got = out + (size_t)i * NV * 4; const uint32_t *want = (const uint32_t *)expect[i]; int diff = 0, first = -1;
            for (int w = 0; w < NV * 4; w++) if (got[w] != want[w]) { if (!diff++) first = w; }
            if (diff) { bad++; fprintf(stderr, "format %#x as %s input: %d words differ, first at vertex %d component %d: got %#x want %#x\n", jobs[i].f, jobs[i].ct == NVN_CT_FLOAT ? "float" : jobs[i].ct == NVN_CT_UINT ? "uint" : "int", diff, first / 4, first % 4, got[first], want[first]); } }
        CHECK(!bad, "every converted attribute equals the CPU's");
        if (round == 0 && gpu_on) { printf("conversion draws in the first round: %llu for %d jobs of %d formats\n", (unsigned long long)(g_vcg_runs - runs0), nj, nfmt); }
    }
    // The vertices a draw reads only (DM_NVN_VCONV_RANGE=1): vertex ids 40..79 of one format read the right elements
    {
        int f = 0x27, es = 4; uint32_t strd = es + 3; size_t span = 1 + (size_t)NV * strd; uint8_t *src = vdata; for (size_t b = 0; b < span; b++) src[b] = (uint8_t)rnd();
        static float expect[NV * 4]; vconv_fill(f, (uint64_t)(uintptr_t)(src + 1), strd, NV, expect);
        state_reset(); memset(&R, 0, sizeof R);
        p_set_rt rt = {.n=1}; rt.color[0] = &t; emit(OP_SET_RT, &rt, sizeof rt);
        p_rast_discard rd = {.on=1}; emit(OP_RAST_DISCARD, &rd, sizeof rd);
        va_st va = {.fmt = (uint32_t)f, .offset = 1, .stream = 0}; p_bind_vattr ba = {.first = 0, .n = 1}; memcpy(&ba.st[0], &va, 4); emit(OP_BIND_VATTR, &ba, sizeof ba);
        p_bind_vstream bt = {.first = 0, .n = 1}; bt.st[0] = (vs_st){strd, 0}; emit(OP_BIND_VSTREAM, &bt, sizeof bt);
        p_bind_vbuf bv = {.first = 0, .n = 1}; bv.r[0] = (NVNbufferRange){(uint64_t)(uintptr_t)src, span}; emit(OP_BIND_VBUF, &bv, sizeof bv);
        p_bind_program bp = {.prog=&pg[0],.stages=3}; emit(OP_BIND_PROGRAM, &bp, sizeof bp);
        p_bind_buf buf = {.stage=0,.index=0,.addr=(uint64_t)(uintptr_t)out,.size=NV * 16}; emit(OP_BIND_SSBO, &buf, sizeof buf);
        p_draw dw = {.prim=NVN_DRAW_PRIMITIVE_POINTS,.first=40,.count=40,.instances=1}; emit(OP_DRAW, &dw, sizeof dw);
        memset(out, 0xEE, NV * 16); execute();
        int ok = 1; for (int v = 40; v < 80; v++) for (int c = 0; c < 4; c++) ok &= out[v * 4 + c] == ((uint32_t *)expect)[v * 4 + c];
        CHECK(ok, "a draw of vertices 40-79 reads the converted elements 40-79");
        CHECK(out[0] == 0xEEEEEEEE && out[80 * 4] == 0xEEEEEEEE, "only the draw's vertices are converted");
    }
    if (gpu_on) { CHECK(g_vcg_runs > runs0 && !g_vcg_cpu, "every conversion ran on the GPU"); }
    else CHECK(g_vcg_runs == 0, "DM_VCONV_GPU=0 makes no GPU conversion");
    printf("vertex conversion on the %s: %d checks, %d failed\n", gpu_on ? "GPU" : "CPU", checks, fails); return fails != 0;
} }
