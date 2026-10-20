#import <UIKit/UIKit.h>
#import "EPPluginHost.h"

static NSMutableArray *failures;
static NSDictionary *Request(NSDictionary *value) {
    NSDictionary *result = [[EPPluginHost shared] request:value];
    if (result[@"error"]) [failures addObject:result[@"error"]];
    return result;
}
static void Check(BOOL condition, NSString *message) { if (!condition) [failures addObject:message]; }

@interface AppDelegate : UIResponder <UIApplicationDelegate>
@property(nonatomic, strong) UIWindow *window;
@end

@implementation AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.window.rootViewController = [[UIViewController alloc] init];
    self.window.rootViewController.view.backgroundColor = UIColor.systemBackgroundColor;
    [self.window makeKeyAndVisible];
    failures = [NSMutableArray array];
    dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
        NSString *documents = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
        NSString *audio = [documents stringByAppendingPathComponent:@"Audio"];
        [NSFileManager.defaultManager createDirectoryAtPath:audio withIntermediateDirectories:YES attributes:nil error:NULL];
        NSData *wav = [NSData dataWithContentsOfFile:[NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"probe.wav"]];
        [wav writeToFile:[audio stringByAppendingPathComponent:@"probe.wav"] atomically:YES];
        Request(@{@"op": @"import", @"path": [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"smoke.plugin"]});
        Request(@{@"op": @"enable", @"id": @"ios_probe", @"enabled": @YES});
        NSDictionary *sent = Request(@{@"op": @"send", @"account": @42, @"params": @{@"message": @"привет"}});
        Check([sent[@"message"] isEqualToString:@"privet"], @"Real Python text hook failed");
        Request(@{@"op": @"event", @"event": @"delete_message", @"account": @42});
        sent = Request(@{@"op": @"send", @"account": @42, @"params": @{@"message": @"привет"}});
        Check([sent[@"message"] isEqualToString:@"privet#1"], @"Native event hook failed");
        NSDictionary *settings = Request(@{@"op": @"settings", @"id": @"ios_probe"});
        Check([settings[@"rows"] count] == 3, @"Settings serialization failed");
        NSArray *menus = Request(@{@"op": @"menus", @"menu": @"chat"})[@"items"];
        Check(menus.count == 1, @"Chat menu registration failed");
        if (menus.count) Request(@{@"op": @"menu_click", @"item": menus[0][@"id"], @"context": @{@"dialog_id": @99}});
        sent = Request(@{@"op": @"send", @"account": @42, @"params": @{@"message": @"привет"}});
        Check([sent[@"message"] isEqualToString:@"привет"], @"Menu callback failed");
        // Let queued UIKit/audio effects finish on the main thread first.
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 2 * NSEC_PER_SEC), dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
            NSArray *logs = Request(@{@"op": @"logs"})[@"lines"];
            for (NSString *line in logs) {
                Check([line rangeOfString:@"Could not play"].location == NSNotFound &&
                      [line rangeOfString:@"cannot decode"].location == NSNotFound,
                      [@"Native playback failed: " stringByAppendingString:line]);
            }
            Request(@{@"op": @"enable", @"id": @"ios_probe", @"enabled": @NO});
            Check([Request(@{@"op": @"menus", @"menu": @"chat"})[@"items"] count] == 0, @"Disable did not clean up menus");
            NSDictionary *report = @{@"passed": @(failures.count == 0), @"failures": failures, @"logs": logs ?: @[]};
            [[NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:NULL]
                writeToFile:[documents stringByAppendingPathComponent:@"smoke-result.json"] atomically:YES];
        });
    });
    return YES;
}
@end

int main(int argc, char *argv[]) {
    @autoreleasepool { return UIApplicationMain(argc, argv, nil, NSStringFromClass(AppDelegate.class)); }
}
