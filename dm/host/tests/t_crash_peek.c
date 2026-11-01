// Unit test (crash.c DM_CRASH_PEEK): a crash report prints guest memory no register points at any more: words at a module offset, the object
// a module slot points to, a list reached through a stack slot and followed by its next field, and an unreadable pointer or unknown module ends
// only that item. crash_peek is called directly with a stack of the test's own; stderr goes to a file the test reads back
#include "../dm.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
void crash_peek(uint64_t sp);
static int checks, failed;
static void expect(const char *name, const char *log, const char *want, int present) {
    checks++;
    if ((strstr(log, want) != NULL) != present) { fprintf(stdout, "%s: \"%s\" %s\n", name, want, present ? "missing" : "present"); failed++; }
}
int main(void) {
    static uint64_t image[16], nodes[3][4], stack[8];
    for (int i = 0; i < 3; i++) { nodes[i][0] = 0xa000 + i; nodes[i][1] = i < 2 ? (uint64_t)(uintptr_t)nodes[i + 1] : 0; nodes[i][2] = 0xb000 + i; }
    image[4] = (uint64_t)(uintptr_t)nodes[0];   // a module slot holding a pointer (image[5] stays 0: a null pointer)
    image[6] = 0xc0ffee;
    stack[6] = (uint64_t)(uintptr_t)&image[4];   // a stack slot at sp+0x30 holding the slot's address
    static module_t mods[1]; strcpy(mods[0].name, "main"); mods[0].base = (uint8_t *)image; mods[0].size = sizeof image;
    g_mod = mods; g_nmod = 1;
    char path[] = "/tmp/t_crash_peek.XXXXXX"; int fd = mkstemp(path); if (fd < 0) return 2;
    fflush(stderr); int saved = dup(2); dup2(fd, 2);
    setenv("DM_CRASH_PEEK", "main+30:1,*main+20:4,**sp+30:3>8x5,*main+28:2,*nomod+8", 1);
    crash_peek((uint64_t)(uintptr_t)stack);
    fflush(stderr); dup2(saved, 2); close(saved);
    char log[8192] = {0}; lseek(fd, 0, SEEK_SET); ssize_t got = read(fd, log, sizeof log - 1); close(fd); unlink(path);
    if (got <= 0) { printf("t_crash_peek: no output\n"); return 1; }
    expect("words at a module offset", log, "[dm] peek main+30:1 [0]", 1);
    expect("words at a module offset (value)", log, " 0xc0ffee", 1);
    expect("the object a slot points to", log, "[dm] peek *main+20:4 [0]", 1);
    expect("the object's words", log, " 0xa000", 1);
    expect("list: first block", log, "[dm] peek **sp+30:3>8x5 [0]", 1);
    expect("list: second block", log, "[dm] peek **sp+30:3>8x5 [1]", 1);
    expect("list: third block", log, "[dm] peek **sp+30:3>8x5 [2]", 1);
    expect("list: third node's word", log, " 0xa002", 1);
    expect("list: stops at the null link", log, "[dm] peek **sp+30:3>8x5 [3]", 0);
    expect("a null pointer is unreadable", log, "[dm] peek *main+28:2: unreadable pointer", 1);
    expect("an unknown module", log, "[dm] peek *nomod+8: no module nomod", 1);
    printf("t_crash_peek: %d checks, %d failed\n", checks, failed);
    return failed != 0;
}
