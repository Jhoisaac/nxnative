// A game may open more than one audio renderer, and the host drives each. Crash Team Racing Nitro-Fueled opens a second one (48 kHz, 6 mix buffers) after its language select and its
// main thread waits on that renderer's event: with one render thread for the whole host the second was never rendered. Checked here: slots and threads per renderer, the order of closing,
// the 3:2 resampler's state, the counters and the catch-up queue per renderer, and the renderer event (My Hero One's Justice 2: the render thread signalled the game's SystemEventType
// after the game had destroyed it on its stack; with the DSP service the host signals the binding it made at open and hands the SDK no event).
#include "../hle.h"
#include <assert.h>
#include <fcntl.h>
#include "../hle_audren.c"

enum { SERVICE_WORK = 0x61d000, NSAMPLES = 160, NFR = 40 };
static int starts, joins, closes, binds, signals;
static void *last_arg, *last_join;
static uint64_t last_signal;
static int binding_live;
static void *bound_ev;
static void *exec_x0[8], *exec_x1[8]; static int execs; static ar_t *exec_stop_ar; static int exec_stop_at;
static int updates_orig, gen_calls;
static _Alignas(16) uint8_t blk[8][64]; static int nblk;
static _Alignas(16) uint8_t sysmem[2][0x400];
static _Alignas(8) uint8_t cmdlist[2][0x20 + 0x148];
static int32_t mixbuf[2][12 * 240];

static size_t sdk_size(const uint8_t *param) { (void)param; return 0x1000; }
static Result sdk_open(void **handle, const uint8_t *param, void *work, size_t size) { (void)param; (void)work; (void)size; handle[0] = blk[nblk]; handle[1] = blk[nblk] + 32; nblk++; return RES_OK; }
// what the SDK leaves in handle[1]: 0 a block of its own, 1 the game's event (My Hero One's Justice 2, Crash Team Racing), 2 a pointer to a slot holding the event (Super Mario Bros. Wonder)
static int h1_shape; static void *sdk_slot;
static Result sdk_open_ev(void **handle, void *ev, const uint8_t *param, void *work, size_t size) {
    Result r = sdk_open(handle, param, work, size);
    if (h1_shape == 1) handle[1] = ev; else if (h1_shape == 2) { sdk_slot = ev; handle[1] = &sdk_slot; }
    return r;
}
static void sdk_close(void *obj, void *state) { (void)obj; (void)state; closes++; }
static void sdk_destroy_event(void *ev) { (void)ev; }
// the wrapper's own signal of the game's struct: 1 reads x1 as a slot (Wonder: ldr x0,[x1], no check on x1), 2 null-checks x1 as the event (MHOJ2), 0 none
static int wrapper_mode, wrapper_signals, wrapper_null_x1;
static void stub_exec(void *x0, void *x1) {
    exec_x0[execs % 8] = x0; exec_x1[execs % 8] = x1; execs++;
    if (wrapper_mode == 1) { if (!x1) wrapper_null_x1++; else if (*(void **)x1) wrapper_signals++; }
    else if (wrapper_mode == 2 && x1) wrapper_signals++;
    if (exec_stop_ar && execs == exec_stop_at) atomic_store(&exec_stop_ar->open, 0);
}
static Result sdk_update(void *sys, void *o, size_t on, void *p, size_t pn, const void *in, size_t inn) { (void)sys; (void)o; (void)on; (void)p; (void)pn; (void)in; (void)inn; updates_orig++; return RES_OK; }
static span_t stub_gen20(void *sys, void *buf, size_t n) { (void)buf; (void)n; gen_calls++; return (span_t){cmdlist[sys == sysmem[1]], sizeof cmdlist[0]}; }
static void nop1(void *p) { (void)p; }
static void nop2(void *p, uint32_t v) { (void)p; (void)v; }
static void nop3(void *p, const void *c, size_t n) { (void)p; (void)c; (void)n; }
void *guest_sym(const char *name) {
    if (!strcmp(name, hle_force_h_ar_WorkSize.name)) return sdk_size;
    if (!strcmp(name, hle_force_h_ar_Open.name)) return sdk_open_ev;
    if (!strcmp(name, hle_force_h_ar_Open0.name)) return sdk_open;
    if (!strcmp(name, hle_force_h_ar_Close.name)) return sdk_close;
    if (!strcmp(name, hle_force_h_ars_Update.name)) return sdk_update;
    if (!strcmp(name, "_ZN2nn2os18DestroySystemEventEPNS0_15SystemEventTypeE")) return sdk_destroy_event;
    if (!strcmp(name, "_ZN2nn5audio29ExecuteAudioRendererRenderingENS0_19AudioRendererHandleE")) return stub_exec;
    // render_once in the SDK 20 layout: the Span version of GenerateCommand, no mutex lookups, a processor that does nothing
    if (!strcmp(name, "_ZN2nn5audio6server17AudioRenderSystem15GenerateCommandENS_4SpanISt4byteEE")) return stub_gen20;
    if (!strcmp(name, "_ZN2nn2os12SdkMutexType4LockEv") || !strcmp(name, "_ZN2nn2os12SdkMutexType6UnlockEv") || !strcmp(name, "_ZN2nn5audio3dsp20CommandListProcessor7ProcessEv")) return nop1;
    if (!strcmp(name, "_ZN2nn5audio3dsp20CommandListProcessor17SetProcessTimeMaxEj")) return nop2;
    if (!strcmp(name, "_ZN2nn5audio3dsp20CommandListProcessor5SetupEPKvm")) return nop3;
    return NULL;
}
void *objmap_get(const void *key) { (void)key; return NULL; }
void objmap_put(const void *key, void *value) { (void)key; (void)value; assert(0); }
void *objmap_del(const void *key) { (void)key; return NULL; }
void *dm_guest_thread_spawn(void (*fn)(void *), void *arg, int prio, size_t stack) { assert(fn == render_main); (void)prio; (void)stack; starts++; last_arg = arg; return arg; }
void dm_guest_thread_join(void *tt) { assert(tt && !atomic_load(&((ar_t *)tt)->open)); last_join = tt; joins++; }
uint64_t now_ns(void) { return 0; }
void *dm_pcmout_open(int ch) { (void)ch; return (void *)1; }
void dm_pcmout_close(void *k) { (void)k; }
void dm_pcmout_start(void *k) { (void)k; }
int dm_pcmout_append(void *k, void *b) { (void)k; (void)b; return 0; }
void *dm_pcmout_released(void *k) { (void)k; return NULL; }
void dm_pcmout_wait(void *k, int ms) { (void)k; (void)ms; }
void hle_bind_system_event(void *ev, int ac) { assert(ac == 1); bound_ev = ev; binds++; }
uint64_t hle_system_event_binding(void *ev) { return ev == bound_ev ? 0x1000 + (uintptr_t)ev % 0x1000 : 0; }
int hle_signal_system_event_binding(uint64_t b) { last_signal = b; signals++; return binding_live; }

// stderr of a step, to look for a log line
static char logbuf[1 << 16];
static int log_fd = -1, saved_fd;
static void log_begin(void) { fflush(stderr); saved_fd = dup(2); log_fd = open("build/t_audren_multi.log", O_CREAT | O_TRUNC | O_RDWR, 0644); assert(log_fd >= 0); dup2(log_fd, 2); }
static const char *log_end(void) {
    fflush(stderr); dup2(saved_fd, 2); close(saved_fd);
    ssize_t n = pread(log_fd, logbuf, sizeof logbuf - 1, 0); assert(n >= 0); logbuf[n] = 0; close(log_fd);
    return logbuf;
}

static uint8_t param[P_SIZE];
static void *dev0_work;
static void set_param(int device) { *(int32_t *)(param + P_DEVICE) = device; }
static Result open_r(int device, void **h, void *ev) {
    set_param(device);
    return ev ? h_ar_Open(h, ev, param, device ? (void *)blk[7] : dev0_work, device ? 64 : SERVICE_WORK) : h_ar_Open0(h, param, device ? (void *)blk[7] : dev0_work, device ? 64 : SERVICE_WORK);
}
static int used_count(void) { int n = 0; for (int i = 0; i < AR_MAX; i++) n += atomic_load(&g_ar[i].used); return n; }

static int sink_id = 0x13;   // render_once takes ID 0x14 for the Span version of GenerateCommand
// one sink command in a list at `rate`: stereo from mix buffers 0 and 1
static size_t build(int k, uint32_t rate, uint32_t samples) {
    uint8_t *l = cmdlist[k]; memset(l, 0, sizeof cmdlist[k]);
    *(uint32_t *)(l + 4) = 1; *(int32_t **)(l + 8) = mixbuf[k]; *(uint32_t *)(l + 0x14) = samples; *(uint32_t *)(l + 0x18) = rate;
    uint8_t *q = l + 0x20; *(uint32_t *)q = 0xcafebabeu; q[4] = 1; q[5] = (uint8_t)sink_id; *(int16_t *)(q + 6) = 0x148;
    *(uint32_t *)(q + 0x130) = 2; ((int16_t *)(q + 0x134))[0] = 0; ((int16_t *)(q + 0x134))[1] = 1;
    return sizeof cmdlist[k];
}
static void fill(int k, int f, int loud) {
    for (int s = 0; s < NSAMPLES; s++) { int32_t v = loud ? (int32_t)(8000 * sin(0.05 * (s + f * NSAMPLES) * (k + 1))) : 0; mixbuf[k][s] = v; mixbuf[k][NSAMPLES + s] = -v / 2; }
}

static void test_resampler(void) {
    static ar_t x, y, alone;
    int16_t o1[FRAME_MAX * 2], o2[FRAME_MAX * 2], ref[NFR][FRAME_MAX * 2], ref_n[NFR];
    size_t n = build(0, 32000, NSAMPLES); build(1, 32000, NSAMPLES);
    for (int f = 0; f < NFR; f++) { fill(0, f, 1); ref_n[f] = (int16_t)capture(&alone, cmdlist[0], n, ref[f]); assert(ref_n[f] == 240); }
    // x (a tone) and y (silence at the same rate, another tone's frames in between) take turns: each gets the output it gets alone
    static ar_t z; int16_t zref[NFR][FRAME_MAX * 2];
    for (int f = 0; f < NFR; f++) { fill(1, f, 1); assert(capture(&z, cmdlist[1], n, zref[f]) == 240); }
    memset(&alone, 0, sizeof alone); memset(&z, 0, sizeof z);
    for (int f = 0; f < NFR; f++) {
        fill(0, f, 1); fill(1, f, 1);
        assert(capture(&x, cmdlist[0], n, o1) == 240 && capture(&y, cmdlist[1], n, o2) == 240);
        assert(!memcmp(o1, ref[f], 240 * 4) && !memcmp(o2, zref[f], 240 * 4));
    }
    assert(atomic_load(&x.frames) == NFR && atomic_load(&y.frames) == NFR && atomic_load(&x.nonsilent) == NFR);
    // counters stay with the renderer: a silent one next to a loud one
    static ar_t quiet, loud;
    for (int f = 0; f < 5; f++) { fill(0, f, 0); assert(capture(&quiet, cmdlist[0], n, o1) == 240); fill(1, f, 1); assert(capture(&loud, cmdlist[1], n, o2) == 240); }
    assert(atomic_load(&quiet.frames) == 5 && atomic_load(&quiet.nonsilent) == 0 && atomic_load(&loud.frames) == 5 && atomic_load(&loud.nonsilent) > 0);
    puts("audren multi: two interleaved 32 kHz renderers match each alone, counters apart");
}

static void test_slots(void) {
    void *h[5][2];
    memset(&g_ar, 0, sizeof g_ar);
    log_begin();
    for (int i = 0; i < 2; i++) assert(!open_r(1, h[i], NULL));
    const char *l = log_end();
    assert(!strstr(l, "a second renderer") && !strstr(l, "[RED]"));
    assert(starts == 2 && used_count() == 2 && g_ar[0].used && g_ar[1].used);
    assert(g_ar[0].h[0] == h[0][0] && g_ar[1].h[0] == h[1][0] && g_ar[0].h[0] != g_ar[1].h[0]);
    assert(g_ar[0].tag[0] == 0 && !strcmp(g_ar[1].tag, "#1"));
    // closing the first stops only the first thread
    h_ar_Close(h[0][0], h[0][1]);
    assert(joins == 1 && last_join == &g_ar[0] && !g_ar[0].used && g_ar[1].used && atomic_load(&g_ar[1].open) && g_ar[1].tt == &g_ar[1]);
    // its slot is reused by the next open
    assert(!open_r(1, h[2], NULL)); assert(g_ar[0].used && g_ar[0].h[0] == h[2][0] && last_arg == &g_ar[0] && used_count() == 2);
    h_ar_Close(h[1][0], h[1][1]);   // the other order: the second first
    assert(joins == 2 && last_join == &g_ar[1] && !g_ar[1].used && g_ar[0].used && atomic_load(&g_ar[0].open));
    h_ar_Close(h[2][0], h[2][1]);
    assert(joins == 3 && used_count() == 0);
    // four fit; a fifth opens in the SDK but is not driven
    int s = starts;
    for (int i = 0; i < 4; i++) assert(!open_r(1, h[i], NULL));
    assert(starts == s + 4 && used_count() == 4);
    log_begin(); assert(!open_r(1, h[4], NULL)); l = log_end();
    assert(starts == s + 4 && used_count() == 4 && strstr(l, "[RED] audren: more than 4 renderers"));
    int j = joins; h_ar_Close(h[4][0], h[4][1]); assert(joins == j && used_count() == 4);   // closing the undriven one touches no thread
    for (int i = 0; i < 4; i++) h_ar_Close(h[i][0], h[i][1]);
    assert(joins == j + 4 && used_count() == 0);
    puts("audren multi: two threads, closes in both orders, slot reuse, a fifth renderer not driven");
}

static void run_rounds(int n) { atomic_store(&g_ar[0].open, 1); execs = 0; signals = 0; wrapper_signals = 0; wrapper_null_x1 = 0; exec_stop_ar = &g_ar[0]; exec_stop_at = n; render_main(&g_ar[0]); }
// device 0 with the SDK's handle[1] in `shape` and a wrapper of the matching kind: the wrapper must not signal the game's struct and the host signals the binding every round
static void event_shape(int shape, int mode, const char *what) {
    memset(&g_ar, 0, sizeof g_ar); bound_ev = NULL; h1_shape = shape; wrapper_mode = mode; binding_live = 1;
    uint8_t ev[64]; memset(ev, 0x24, sizeof ev); uint8_t poison[64]; memcpy(poison, ev, sizeof ev);
    void *h[2]; int b = binds;
    log_begin(); assert(!open_r(0, h, ev)); const char *l = log_end();
    assert(!strstr(l, "[RED]") && strstr(l, what));
    assert(binds == b + 1 && g_ar[0].ev_binding == hle_system_event_binding(ev) && g_ar[0].ev_binding && g_ar[0].ev_shape == (shape == 1 ? EV_DIRECT : EV_SLOT));
    run_rounds(3);
    assert(execs == 3 && signals == 3 && last_signal == g_ar[0].ev_binding && wrapper_signals == 0 && wrapper_null_x1 == 0);
    for (int i = 0; i < 3; i++) assert(exec_x0[i] == h[0] && exec_x1[i] != h[1] && exec_x1[i] != (void *)ev);
    if (shape == 1) { for (int i = 0; i < 3; i++) assert(exec_x1[i] == NULL); }
    else for (int i = 0; i < 3; i++) assert(exec_x1[i] == (void *)&g_ar[0].ev_null && *(void **)exec_x1[i] == NULL);
    // the game closed the write handle (and destroyed the struct): the signal finds nothing, and the struct is never read
    binding_live = 0; run_rounds(3);
    assert(execs == 3 && signals == 3 && wrapper_signals == 0 && wrapper_null_x1 == 0 && !memcmp(ev, poison, sizeof ev));
    h_ar_Close(h[0], h[1]);
    exec_stop_ar = NULL; t_ar = NULL;
}
static void test_event(void) {
    event_shape(1, 2, "takes the event itself");
    event_shape(2, 1, "through a slot");
    // neither: h[1] is kept as before the change, the host signals nothing, and the red line names both values
    memset(&g_ar, 0, sizeof g_ar); bound_ev = NULL; h1_shape = 0; wrapper_mode = 0;
    uint8_t ev[64]; void *h[2], *h1[2];
    log_begin(); assert(!open_r(0, h, ev)); const char *l = log_end();
    char want[64]; snprintf(want, sizeof want, "[RED] audren: unknown handle shape: h[1] %p", h[1]);
    assert(strstr(l, want) && g_ar[0].ev_shape == EV_NONE && !g_ar[0].ev_binding);
    run_rounds(2);
    assert(execs == 2 && signals == 0 && exec_x1[0] == h[1] && exec_x1[1] == h[1]);
    h_ar_Close(h[0], h[1]);
    // CPU rendering: the SDK's local event is alive by contract, the wrapper signals it
    bound_ev = NULL;
    assert(!open_r(1, h1, ev));
    assert(!g_ar[0].ev_binding && g_ar[0].ev_shape == EV_NONE);
    run_rounds(2);
    assert(execs == 2 && signals == 0 && exec_x1[0] == h1[1] && exec_x1[1] == h1[1]);
    h_ar_Close(h1[0], h1[1]);
    exec_stop_ar = NULL; t_ar = NULL; h1_shape = 0;
    puts("audren multi: device 0 signals its binding in both wrapper shapes (event itself: NULL; slot: a NULL slot), the wrapper signals nothing; unknown shape keeps h[1] and prints the red line; CPU keeps the SDK's event");
}

static void test_catchup(void) {
    memset(&g_ar, 0, sizeof g_ar); updates_orig = 0; sink_id = 0x14;
    void *h[2][2];
    assert(!open_r(1, h[0], NULL)); assert(!open_r(1, h[1], NULL));
    for (int k = 0; k < 2; k++) { memset(sysmem[k], 0, sizeof sysmem[k]); *(int32_t *)(sysmem[k] + 0x48) = 1; *(int32_t *)(sysmem[k] + 0x4c) = 1; *(uint8_t **)(sysmem[k] + 0xf8) = cmdlist[k]; *(size_t *)(sysmem[k] + 0x100) = sizeof cmdlist[k]; }
    for (int k = 0; k < 2; k++) { build(k, 48000, 240); for (int s = 0; s < 240; s++) { mixbuf[k][s] = 100; mixbuf[k][240 + s] = -100; } }
    // a system nobody knows (two renderers open, neither has rendered): the SDK's update, nothing else
    static _Alignas(16) uint8_t other[0x400]; memcpy(other, sysmem[0], sizeof other);
    assert(h_ars_Update(other, NULL, 0, NULL, 0, NULL, 0) == RES_OK && updates_orig == 1 && !atomic_load(&g_ar[0].updates) && !atomic_load(&g_ar[1].updates) && !g_ar[0].sys && !g_ar[1].sys);
    // each learns its system on its render thread
    t_ar = &g_ar[0]; assert(h_ars_Exec(sysmem[0]) == RES_OK); t_ar = &g_ar[1]; assert(h_ars_Exec(sysmem[1]) == RES_OK); t_ar = NULL;
    assert(g_ar[0].sys == sysmem[0] && g_ar[1].sys == sysmem[1] && atomic_load(&g_ar[0].renders) == 1 && atomic_load(&g_ar[1].renders) == 1 && g_ar[0].frame_n == 240 && g_ar[1].frame_n == 240);
    // a call from no render thread follows its system; an unknown one renders and discards
    assert(h_ars_Exec(sysmem[1]) == RES_OK && atomic_load(&g_ar[1].renders) == 2 && atomic_load(&g_ar[0].renders) == 1);
    uint64_t r0 = atomic_load(&g_ar[0].renders), r1 = atomic_load(&g_ar[1].renders);
    assert(h_ars_Exec(other) == RES_OK && atomic_load(&g_ar[0].renders) == r0 && atomic_load(&g_ar[1].renders) == r1);
    // updates: the first of each renderer renders nothing extra; with nothing rendered since, only that renderer catches up
    uint32_t gc = gen_calls;
    assert(h_ars_Update(sysmem[0], NULL, 0, NULL, 0, NULL, 0) == RES_OK);
    assert(atomic_load(&g_ar[0].catchups) == 0 && g_ar[0].last_r == 1);
    assert(h_ars_Update(sysmem[0], NULL, 0, NULL, 0, NULL, 0) == RES_OK);
    assert(atomic_load(&g_ar[0].catchups) == 1 && atomic_load(&g_ar[0].renders) == 2 && atomic_load(&g_ar[0].cq_tail) == 1 && g_ar[0].cq_n[0] == 240 && g_ar[0].cq[0][0] == 100);
    assert(atomic_load(&g_ar[1].catchups) == 0 && atomic_load(&g_ar[1].cq_tail) == 0 && atomic_load(&g_ar[1].updates) == 0 && gen_calls >= (int)gc + 1);
    // the other keeps its own count: rendered since its last update, so no catch-up
    assert(h_ars_Update(sysmem[1], NULL, 0, NULL, 0, NULL, 0) == RES_OK);
    atomic_fetch_add(&g_ar[1].renders, 1);
    assert(h_ars_Update(sysmem[1], NULL, 0, NULL, 0, NULL, 0) == RES_OK);
    assert(atomic_load(&g_ar[1].catchups) == 0 && atomic_load(&g_ar[1].updates) == 2 && atomic_load(&g_ar[0].updates) == 2);
    h_ar_Close(h[0][0], h[0][1]); h_ar_Close(h[1][0], h[1][1]);
    // one renderer open and its system not learned yet: the update is its (as with the single renderer before)
    assert(!open_r(1, h[0], NULL));
    assert(h_ars_Update(sysmem[0], NULL, 0, NULL, 0, NULL, 0) == RES_OK && g_ar[0].sys == sysmem[0] && atomic_load(&g_ar[0].updates) == 1);
    h_ar_Close(h[0][0], h[0][1]);
    puts("audren multi: catch-up counters, queue and system lookup per renderer");
}

int main(void) {
    const uint32_t words[] = {48000, 240, 132, 19, 138, 1, 16, 0, 0, 85, 1800, 0, 0, 0x38564552};
    memcpy(param, words, sizeof words);
    assert(!posix_memalign(&dev0_work, WORK_PAGE, SERVICE_WORK));
    test_resampler();
    test_slots();
    test_event();
    test_catchup();
    free(dev0_work);
    return 0;
}
