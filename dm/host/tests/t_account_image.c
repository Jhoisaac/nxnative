// The local user's profile image (hle_account.c LoadProfileImage): a JPEG that ImageIO decodes to 256x256, copied whole into the game's 0x20000-byte buffer with its size, and cut to a
// smaller buffer with the full size still reported; the hook is looked up by its mangled name in the real swforce registrations
#include "../hle_account.c"
#include <mach-o/getsect.h>
#include <ImageIO/ImageIO.h>

static int checks, fails;
void hle_signal_system_event(void *g) { (void)g; }   // the async contexts' completion events, not used here
// The big-stack take-overs' stubs (HLE_FORCE_BIG) jump here with the implementation in x16; off a guest stack the real entry calls it straight
__asm__(".text\n.p2align 2\n.globl _dm_bigstack_enter\n_dm_bigstack_enter:\n    br x16\n");
extern const struct mach_header_64 _mh_execute_header;
#define CHECK(c, msg) do { checks++; if (!(c)) { fails++; fprintf(stderr, "FAIL: %s\n", msg); } } while (0)
static void *hook(const char *name) {
    unsigned long bytes = 0;
    const hle_force_ent *e = (const hle_force_ent *)getsectiondata(&_mh_execute_header, "__DATA", "swforce", &bytes);
    void *fn = NULL; unsigned count = 0;
    for (size_t i = 0; e && i < bytes / sizeof *e; i++) if (!strcmp(e[i].name, name)) { count++; fn = (void *)e[i].fn; }
    CHECK(count == 1 && fn, name);
    return count == 1 ? fn : NULL;
}
int main(void) {
    Result (*load)(uint64_t *, void *, uint64_t, const Uid *) = hook("_ZN2nn7account16LoadProfileImageEPmPvmRKNS0_3UidE");
    if (!load) return 1;
    static uint8_t buf[0x20000]; uint64_t n = 0;
    CHECK(load(&n, buf, sizeof buf, &k_uid) == RES_OK, "the image loads");
    CHECK(n == sizeof k_profile_jpeg && !memcmp(buf, k_profile_jpeg, n), "the whole image and its size");
    CHECK(n <= 0x20000 && buf[0] == 0xff && buf[1] == 0xd8 && buf[n - 2] == 0xff && buf[n - 1] == 0xd9, "a JPEG within the account's limit");
    CFDataRef d = CFDataCreate(NULL, buf, (CFIndex)n);
    CGImageSourceRef src = CGImageSourceCreateWithData(d, NULL);
    CGImageRef im = src ? CGImageSourceCreateImageAtIndex(src, 0, NULL) : NULL;
    CHECK(im && CGImageGetWidth(im) == 256 && CGImageGetHeight(im) == 256, "it decodes to 256x256");
    if (im) CGImageRelease(im);
    if (src) CFRelease(src);
    CFRelease(d);
    uint8_t small[16]; memset(small, 0, sizeof small); n = 0;
    CHECK(load(&n, small, sizeof small, &k_uid) == RES_OK && n == sizeof k_profile_jpeg && !memcmp(small, k_profile_jpeg, sizeof small), "a small buffer gets the image's start and its size");
    printf("account image: %d checks, %d failed\n", checks, fails);
    return fails != 0;
}
