// Core Haptics adapts the game's bands; it cannot reproduce the Switch's exact waveforms.
// All engines and players belong to one serial queue. Guest threads enqueue ordered snapshots only.
#import "haptics_apple.h"
#import <CoreHaptics/CoreHaptics.h>
#import <TargetConditionals.h>
#if TARGET_OS_IPHONE
#import <UIKit/UIKit.h>
#import <AVFAudio/AVFAudio.h>
#else
#import <AppKit/AppKit.h>
#import <IOKit/hid/IOHIDManager.h>
#endif
#include <math.h>
#include <pthread.h>
#include <stdatomic.h>
#include <time.h>

@interface DmRumbleChannel : NSObject
@property(nonatomic) CHHapticEngine *engine;
@property(nonatomic) id<CHHapticAdvancedPatternPlayer> pattern;
@property(nonatomic, copy) CHHapticEngine *(^createEngine)(NSError **);
@property(nonatomic, copy) NSString *target;
@property(nonatomic, copy) void (^fallback)(NSTimeInterval);
@property(nonatomic) int player;
@property(nonatomic) uint64_t generation;
@property(nonatomic) uint64_t silenceGeneration;
@property(nonatomic) NSTimeInterval retryAfter;
@property(nonatomic) unsigned failures;
- (void)apply:(dm_haptic_level)level;
- (void)stop;
@end

static dispatch_queue_t queue;
static NSMutableArray<DmRumbleChannel *> *channels[DM_PLAYERS];
static GCController *controllers[DM_PLAYERS];
#if TARGET_OS_IPHONE
static BOOL phoneSupported;
#endif
static float gain = 1;
static pthread_mutex_t routeLock = PTHREAD_MUTEX_INITIALIZER;
static unsigned errors;
static NSTimeInterval now(void) {
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec / 1e9;
}
static void report(NSError *e, NSString *target, const char *stage) {
    if (++errors <= 8 || errors % 64 == 0) {
        fprintf(stderr, "[RED] haptics: %s %s: %s (%s %ld)\n", target.UTF8String, stage,
                e.localizedDescription.UTF8String ?: "engine unavailable", e.domain.UTF8String ?: "no error", (long)e.code);
        NSError *underlying = e.userInfo[NSUnderlyingErrorKey];
        if (underlying) fprintf(stderr, "[RED] haptics: underlying %s %ld: %s\n", underlying.domain.UTF8String,
                                (long)underlying.code, underlying.userInfo[NSDebugDescriptionErrorKey] ?
                                [underlying.userInfo[NSDebugDescriptionErrorKey] UTF8String] : underlying.localizedDescription.UTF8String);
    }
}

#if !TARGET_OS_IPHONE
static void report_hid(IOReturn r) { if (++errors <= 8 || errors % 64 == 0) fprintf(stderr, "[RED] haptics: controller HID rumble report: IOReturn 0x%x\n", r); }
#endif

@implementation DmRumbleChannel
- (void)stop {
    self.generation++; self.silenceGeneration++;
    self.engine.stoppedHandler = ^(CHHapticEngineStoppedReason reason) { (void)reason; }; self.engine.resetHandler = ^{};
    [self.pattern stopAtTime:CHHapticTimeImmediate error:nil]; self.pattern = nil;
    [self.engine stopWithCompletionHandler:nil];   // the engine stays: the next effect restarts it
}
- (void)failed:(NSError *)error stage:(const char *)stage {
    report(error, self.target, stage);
    [self stop]; self.engine = nil;   // A failed helper connection must not be reused for every later vibration.
    self.failures = MIN(self.failures + 1, 4u);
    self.retryAfter = now() + (1u << (self.failures - 1));
    dm_haptics_clear(self.player);
}
- (void)engineFailed:(NSError *)error stage:(const char *)stage {
    [self failed:error stage:stage];
    // Only an engine that cannot be made or started moves a split route to the default locality;
    // a player or parameter failure (a service reset, say) is retried on the same handle.
    if (self.fallback) self.fallback(self.retryAfter);
}
- (void)apply:(dm_haptic_level)level {
    uint64_t silence = ++self.silenceGeneration;
    NSError *error = nil;
    if (!self.pattern) {
        if (level.intensity == 0) return;
        if (now() < self.retryAfter) {
            // Discard this effect, so an identical fresh send after the backoff is not deduplicated away.
            dm_haptics_clear(self.player); return;
        }
        if (!self.engine) {
            self.engine = self.createEngine(&error);
            if (!self.engine) { [self engineFailed:error stage:"create engine"]; return; }
            self.engine.playsHapticsOnly = YES; self.engine.autoShutdownEnabled = NO;
        }
        __weak DmRumbleChannel *weak = self;
        uint64_t generation = ++self.generation;
        void (^reset)(void) = ^{
            dispatch_async(queue, ^{
                DmRumbleChannel *c = weak; if (!c || c.generation != generation) return;
                [c stop];
                dm_haptics_clear(c.player);   // queued effects from before an interruption cannot restart
            });
        };
        self.engine.stoppedHandler = ^(CHHapticEngineStoppedReason reason) { (void)reason; reset(); };
        self.engine.resetHandler = reset;
        // Startup can itself fail or reset the service: install handlers before contacting it.
        if (![self.engine startAndReturnError:&error]) { [self engineFailed:error stage:"start engine"]; return; }
        CHHapticEvent *event = [[CHHapticEvent alloc] initWithEventType:CHHapticEventTypeHapticContinuous parameters:@[
            [[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticIntensity value:1],
            [[CHHapticEventParameter alloc] initWithParameterID:CHHapticEventParameterIDHapticSharpness value:0.5]
        ] relativeTime:0 duration:30];
        CHHapticPattern *pattern = [[CHHapticPattern alloc] initWithEvents:@[event] parameters:@[] error:&error];
        self.pattern = pattern ? [self.engine createAdvancedPlayerWithPattern:pattern error:&error] : nil;
        if (!self.pattern) {
            // The Xbox Wireless Controller on the Mac starts its left handle's engine, but making its player fails with NSCocoaErrorDomain 4097 (the helper connection was
            // interrupted) on every try: such a lost helper connection counts as the engine failing, so a split route falls back to the default locality like an engine
            // that cannot start; other player errors are retried on the same handle
            if ([error.domain isEqualToString:NSCocoaErrorDomain] && (error.code == 4097 || error.code == 4099)) [self engineFailed:error stage:"create player"];
            else [self failed:error stage:"create player"];
            return;
        }
        self.pattern.loopEnabled = YES;
        self.pattern.isMuted = YES;
        if (![self.pattern startAtTime:CHHapticTimeImmediate error:&error]) { [self failed:error stage:"start player"]; return; }
    }
    // Controls live outside the loop: the loop boundary never replays an initial intensity.
    NSArray *parameters = @[
        [[CHHapticDynamicParameter alloc] initWithParameterID:CHHapticDynamicParameterIDHapticIntensityControl value:level.intensity relativeTime:0],
        [[CHHapticDynamicParameter alloc] initWithParameterID:CHHapticDynamicParameterIDHapticSharpnessControl value:level.sharpness - 0.5f relativeTime:0]
    ];
    if (![self.pattern sendParameters:parameters atTime:CHHapticTimeImmediate error:&error]) {
        [self failed:error stage:"send parameters"]; return;
    }
    self.failures = 0;
    self.pattern.isMuted = NO;
    if (level.intensity == 0) {
        // Reuse a warm player for nearby pulses, then release idle hardware. This never times out an active effect.
        __weak DmRumbleChannel *weak = self;
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, NSEC_PER_SEC), queue, ^{
            DmRumbleChannel *c = weak; if (c && c.silenceGeneration == silence) [c stop];
        });
    }
}
@end

#if !TARGET_OS_IPHONE
// An Xbox Wireless Controller over Bluetooth on the Mac takes its rumble as HID output report 3, as SDL's HIDAPI driver sends it: an enable mask, the left and right
// trigger motors, the strong (left grip) and weak (right grip) motors in percent, then duration and delay in 10 ms units and a repeat count. It is the route when Core
// Haptics fails at every locality: on the Mac every player of this controller failed with NSCocoaErrorDomain 4097, the connection to gamecontrollerd's haptics service
// interrupted, Default and Handles included. Each report holds its value for 1 s and a value that is not zero is sent again every 0.5 s, so a held value lasts as a
// Switch motor's does, yet the motors stop within a second when the host ends without stopping them (Ctrl-C, SIGTERM's _exit, a crash) or a report fails, where a
// report held for about 10 minutes outlived the host (found on Super Mario Odyssey, whose pad kept rumbling)
enum { HID_HOLD = 100 };   // one report's duration in 10 ms units, no repeats
static const double HID_REFRESH = 0.5;   // seconds between sends of a held value
static IOHIDDeviceRef xbox_hid_find(GCController *controller, NSArray *taken) {
    if (![controller.vendorName hasPrefix:@"Xbox"]) return NULL;
    static IOHIDManagerRef manager;
    if (!manager) {
        manager = IOHIDManagerCreate(kCFAllocatorDefault, kIOHIDOptionsTypeNone);
        IOHIDManagerSetDeviceMatching(manager, (__bridge CFDictionaryRef)@{@kIOHIDVendorIDKey: @0x045E, @kIOHIDPrimaryUsagePageKey: @1, @kIOHIDPrimaryUsageKey: @5});
        if (IOHIDManagerOpen(manager, kIOHIDOptionsTypeNone) != kIOReturnSuccess) { CFRelease(manager); manager = NULL; return NULL; }
    }
    NSSet *devices = CFBridgingRelease(IOHIDManagerCopyDevices(manager));
    // GameController does not say which HID device a controller is: with several Xbox pads each player takes the first one no other player holds
    for (id d in devices) {
        IOHIDDeviceRef dev = (__bridge IOHIDDeviceRef)d;
        NSString *transport = (__bridge NSString *)IOHIDDeviceGetProperty(dev, CFSTR(kIOHIDTransportKey));
        if (![transport hasPrefix:@"Bluetooth"] || [taken containsObject:d]) continue;
        if (IOHIDDeviceOpen(dev, kIOHIDOptionsTypeNone) == kIOReturnSuccess) return (IOHIDDeviceRef)CFRetain(dev);
    }
    return NULL;
}
static IOReturn xbox_hid_write(IOHIDDeviceRef dev, const uint8_t *report, size_t n) { return IOHIDDeviceSetReport(dev, kIOHIDReportTypeOutput, report[0], report, n); }
static IOHIDDeviceRef (*hid_find)(GCController *, NSArray *) = xbox_hid_find;
static IOReturn (*hid_write)(IOHIDDeviceRef, const uint8_t *, size_t) = xbox_hid_write;

@interface DmHidRumble : DmRumbleChannel
@property(nonatomic) IOHIDDeviceRef device;
@property(nonatomic) int strong, weak;
@property(nonatomic) uint64_t hold;   // the held value's refresh chain; a newer value or a stop ends it
- (void)send:(dm_haptic_state)s;
@end
@implementation DmHidRumble
- (BOOL)report:(int)strong weak:(int)weak {
    const uint8_t packet[] = {0x03, 0x0F, 0, 0, (uint8_t)strong, (uint8_t)weak, HID_HOLD, 0x00, 0x00};
    IOReturn r = hid_write(self.device, packet, sizeof packet);
    if (r == kIOReturnSuccess) return YES;
    report_hid(r);
    CFRelease(self.device); self.device = NULL;   // gone or refused: the next connection configures the route again, and the last report runs out by itself
    return NO;
}
- (void)write:(int)strong weak:(int)weak {
    if (!self.device || (strong == self.strong && weak == self.weak)) return;
    if (![self report:strong weak:weak]) return;
    self.strong = strong; self.weak = weak;
    uint64_t hold = ++self.hold;
    if (strong || weak) [self refresh:hold];
}
- (void)refresh:(uint64_t)hold {
    __weak DmHidRumble *weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(HID_REFRESH * NSEC_PER_SEC)), queue, ^{
        DmHidRumble *c = weakSelf;
        if (c && c.hold == hold && c.device && [c report:c.strong weak:c.weak]) [c refresh:hold];
    });
}
// Each motor's level is its Core Haptics intensity, linear with the gain, as every other controller's: a curve that raised low amplitudes ((a + a^0.35) / 2, 0.1 → 27%)
// turned the faint rumble a game holds through a cutscene or plays at each step into a strong one (found on Super Mario Odyssey, whose pad rumbled all through its opening)
static int hid_percent(const dm_vibration *v) { return (int)lroundf(dm_haptics_level(v, 1, gain).intensity * 100); }
- (void)send:(dm_haptic_state)s { [self write:hid_percent(&s.motor[0]) weak:hid_percent(&s.motor[1])]; }
- (void)stop { [self write:0 weak:0]; }
- (void)dealloc { if (self.device) CFRelease(self.device); }
@end
#endif

// Each state is the whole motor pair, so a HID report only needs the newest: a state with a newer one behind it on the queue is dropped. A HID report is a synchronous Bluetooth
// write; Super Mario Odyssey changes its rumble about 200 times a second through its opening cutscene, faster than the controller takes reports, and the queue fell minutes
// behind: the pad rumbled long after the cutscene had set 0
static _Atomic uint64_t newest[DM_PLAYERS];
static void apply(dm_haptic_state s) {
    uint64_t seq = atomic_fetch_add(&newest[s.player], 1) + 1;
    dispatch_async(queue, ^{ @autoreleasepool {
        if (s.epoch != dm_haptics_epoch(s.player)) return;
        NSArray<DmRumbleChannel *> *out = channels[s.player];
#if !TARGET_OS_IPHONE
        if ([out.firstObject isKindOfClass:DmHidRumble.class]) { if (seq == atomic_load(&newest[s.player])) [(DmHidRumble *)out.firstObject send:s]; return; }
#endif
        for (NSUInteger i = 0; i < out.count; i++) {
            if (s.epoch != dm_haptics_epoch(s.player)) break;   // a failed channel may replace this route
            dm_haptic_level level = out.count == 2 ? dm_haptics_level(&s.motor[i], 1, gain) : dm_haptics_level(s.motor, 2, gain);
            [out[i] apply:level];
        }
    } });
}
static void add_engine(int p, NSString *target, CHHapticEngine *(^create)(NSError **)) {
    DmRumbleChannel *c = [DmRumbleChannel new]; c.createEngine = create; c.target = target; c.player = p;
    [channels[p] addObject:c];
}
#if !TARGET_OS_IPHONE
// The last fallback: when the default locality cannot make an engine or a player either, an Xbox controller is driven by its HID report
static void hid_fallback(int p, GCController *controller) {
    __weak NSArray *route = channels[p];
    channels[p].lastObject.fallback = ^(NSTimeInterval retryAfter) {
        (void)retryAfter;
        if (!route || channels[p] != route) return;
        NSMutableArray *taken = [NSMutableArray new];
        for (int q = 0; q < DM_PLAYERS; q++) if (q != p && [channels[q].firstObject isKindOfClass:DmHidRumble.class]) {
            IOHIDDeviceRef d = ((DmHidRumble *)channels[q].firstObject).device; if (d) [taken addObject:(__bridge id)d];
        }
        IOHIDDeviceRef dev = hid_find(controller, taken);
        if (!dev) return;
        for (DmRumbleChannel *old in channels[p]) [old stop];
        DmHidRumble *c = [DmHidRumble new]; c.device = dev; c.player = p; c.target = @"controller HID";
        channels[p] = [NSMutableArray arrayWithObject:c];
        dm_haptics_route(p, 1);
        fprintf(stderr, "haptics: player %d uses the controller's HID rumble report\n", p + 1);
    };
}
#endif
static void default_controller(int p, GCController *controller, NSTimeInterval retryAfter) {
    GCDeviceHaptics *h = controller.haptics;
    add_engine(p, @"controller default", ^CHHapticEngine *(NSError **e) { (void)e; return [h createEngineWithLocality:GCHapticsLocalityDefault]; });
    channels[p].lastObject.retryAfter = retryAfter;
#if !TARGET_OS_IPHONE
    hid_fallback(p, controller);
#endif
}
static void configure(int p, GCController *controller) {
    for (DmRumbleChannel *c in channels[p]) [c stop];
    channels[p] = [NSMutableArray new];
    if (controller) {
        GCDeviceHaptics *h = controller.haptics;
        NSSet *localities = h.supportedLocalities;
        if ([localities containsObject:GCHapticsLocalityLeftHandle] && [localities containsObject:GCHapticsLocalityRightHandle]) {
            add_engine(p, @"controller left handle", ^CHHapticEngine *(NSError **e) { (void)e; return [h createEngineWithLocality:GCHapticsLocalityLeftHandle]; });
            add_engine(p, @"controller right handle", ^CHHapticEngine *(NSError **e) { (void)e; return [h createEngineWithLocality:GCHapticsLocalityRightHandle]; });
            // Advertised handle localities can still fail to start. Fall back to the standard
            // controller engine, once, rather than keeping two unusable helper connections.
            __weak NSArray *route = channels[p];
            for (DmRumbleChannel *c in channels[p]) c.fallback = ^(NSTimeInterval retryAfter) {
                if (!route || channels[p] != route) return;
                for (DmRumbleChannel *old in channels[p]) [old stop];
                channels[p] = [NSMutableArray new];
                default_controller(p, controller, retryAfter);
                dm_haptics_route(p, 1);
                fprintf(stderr, "haptics: player %d retrying with the default controller locality\n", p + 1);
            };
        }
        else if (localities.count) default_controller(p, controller, 0);
        fprintf(stderr, "haptics: player %d controller %s, localities %s, %lu channels\n", p + 1,
                controller.vendorName.UTF8String ?: "unknown", [[localities.allObjects sortedArrayUsingSelector:@selector(compare:)] componentsJoinedByString:@", "].UTF8String ?: "none", (unsigned long)channels[p].count);
    }
#if TARGET_OS_IPHONE
    else if (!p && phoneSupported) {
        // Do not initialize the phone's engine before the game's audio session is active.
        add_engine(p, @"phone", ^CHHapticEngine *(NSError **e) { return [[CHHapticEngine alloc] initWithAudioSession:AVAudioSession.sharedInstance error:e]; });
    }
#endif
    dm_haptics_route(p, channels[p].count != 0);
}
void dm_haptics_apple_controller(int p, GCController *controller) {
    if (!queue || p < 0 || p >= DM_PLAYERS) return;
    pthread_mutex_lock(&routeLock);
    if (controllers[p] != controller) {
        controllers[p] = controller;
        dm_haptics_route(p, 0);   // invalidate queued work before changing hardware
        dispatch_sync(queue, ^{ configure(p, controller); });
    }
    pthread_mutex_unlock(&routeLock);
}
static void suspend(unsigned reason, BOOL on) {
    dm_haptics_suspend(reason, on);
    void (^stop)(void) = ^{
        for (int p = 0; p < DM_PLAYERS; p++) for (DmRumbleChannel *c in channels[p]) [c stop];
    };
    if (on) { if (dispatch_get_specific(&queue)) stop(); else dispatch_sync(queue, stop); }
}
void dm_haptics_apple_shutdown(void) {
    if (queue) suspend(DM_HAPTICS_INACTIVE, YES);
}
void dm_haptics_apple_init(void) {
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        queue = dispatch_queue_create("dm.rumble", DISPATCH_QUEUE_SERIAL);
        dispatch_queue_set_specific(queue, &queue, &queue, NULL);
        const char *e = getenv("DM_RUMBLE_GAIN");
        if (e) { float v = strtof(e, NULL); if (isfinite(v)) gain = fmaxf(0, fminf(3, v)); }
        e = getenv("DM_RUMBLE");
        dm_haptics_init(apply, !e || atoi(e) != 0);
#if TARGET_OS_IPHONE
        phoneSupported = CHHapticEngine.capabilitiesForHardware.supportsHaptics;
#endif
        dispatch_sync(queue, ^{ configure(0, nil); });
        NSNotificationCenter *nc = NSNotificationCenter.defaultCenter;
#if TARGET_OS_IPHONE
        [nc addObserverForName:UIApplicationWillResignActiveNotification object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; suspend(DM_HAPTICS_INACTIVE, YES); }];
        [nc addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; suspend(DM_HAPTICS_INACTIVE, NO); }];
        [nc addObserverForName:UIApplicationWillTerminateNotification object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; dm_haptics_apple_shutdown(); }];
        [nc addObserverForName:AVAudioSessionInterruptionNotification object:nil queue:nil usingBlock:^(NSNotification *n) {
            suspend(DM_HAPTICS_INTERRUPTED, [n.userInfo[AVAudioSessionInterruptionTypeKey] unsignedIntegerValue] == AVAudioSessionInterruptionTypeBegan);
        }];
        [nc addObserverForName:AVAudioSessionRouteChangeNotification object:nil queue:nil usingBlock:^(NSNotification *n) {
            (void)n; dm_haptics_clear(0);
        }];
#else
        [nc addObserverForName:NSApplicationWillResignActiveNotification object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; suspend(DM_HAPTICS_INACTIVE, YES); }];
        [nc addObserverForName:NSApplicationDidBecomeActiveNotification object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; suspend(DM_HAPTICS_INACTIVE, NO); }];
        [nc addObserverForName:NSApplicationWillTerminateNotification object:nil queue:nil usingBlock:^(NSNotification *n) { (void)n; dm_haptics_apple_shutdown(); }];
#endif
        atexit(dm_haptics_apple_shutdown);
    });
}
