#import "EPPluginHost.h"
#import "EPPluginManagerController.h"
#import <UIKit/UIKit.h>
#import <AVFoundation/AVFoundation.h>
#include <Python/Python.h>

static const void *EPQueueKey = &EPQueueKey;

@interface EPPluginHost ()
@property(nonatomic, strong) dispatch_queue_t queue;
@property(nonatomic, copy) NSString *startupError;
@property(nonatomic) BOOL started;
@property(nonatomic) PyObject *dispatcher;
@property(nonatomic, strong) NSMutableDictionary<NSString *, AVAudioPlayer *> *players;
@property(nonatomic, strong) NSMutableArray<NSString *> *nativeLogs;
@property(nonatomic, strong) NSMutableArray *observerTokens;
- (void)nativeCommand:(NSDictionary *)command;
@end

static PyObject *EPSend(PyObject *self, PyObject *args) {
    const char *json;
    if (!PyArg_ParseTuple(args, "s", &json)) return NULL;
    NSData *data = [[NSString stringWithUTF8String:json] dataUsingEncoding:NSUTF8StringEncoding];
    NSDictionary *command = [NSJSONSerialization JSONObjectWithData:data options:0 error:NULL];
    if (![command isKindOfClass:[NSDictionary class]]) {
        PyErr_SetString(PyExc_ValueError, "Native command must be an object");
        return NULL;
    }
    dispatch_async(dispatch_get_main_queue(), ^{ [[EPPluginHost shared] nativeCommand:command]; });
    Py_RETURN_NONE;
}

static PyMethodDef EPMethods[] = {
    {"send", EPSend, METH_VARARGS, "Queue a native iOS effect."},
    {NULL, NULL, 0, NULL}
};
static struct PyModuleDef EPModule = {PyModuleDef_HEAD_INIT, "_extera_native", NULL, -1, EPMethods};
static PyObject *PyInit_extera_native(void) { return PyModule_Create(&EPModule); }

static UIViewController *EPTopController(void) {
    UIWindow *window = nil;
    for (UIScene *scene in UIApplication.sharedApplication.connectedScenes) {
        if (scene.activationState != UISceneActivationStateForegroundActive ||
            ![scene isKindOfClass:[UIWindowScene class]]) continue;
        for (UIWindow *candidate in ((UIWindowScene *)scene).windows) {
            if (candidate.isKeyWindow) { window = candidate; break; }
        }
        if (window) break;
    }
    UIViewController *controller = window.rootViewController;
    while (controller.presentedViewController && !controller.presentedViewController.isBeingDismissed) {
        controller = controller.presentedViewController;
    }
    return controller;
}

@implementation EPPluginHost
+ (instancetype)shared {
    static EPPluginHost *host;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ host = [[self alloc] init]; });
    return host;
}

- (instancetype)init {
    if ((self = [super init])) {
        _queue = dispatch_queue_create("app.exteragram.python", DISPATCH_QUEUE_SERIAL);
        dispatch_queue_set_specific(_queue, EPQueueKey, (void *)EPQueueKey, NULL);
        _players = [NSMutableDictionary dictionary];
        _nativeLogs = [NSMutableArray array];
        _observerTokens = [NSMutableArray array];
        // Effects are always scheduled onto main; Python callbacks run on the
        // serial interpreter queue and must never wait synchronously on UIKit.
        NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
        for (NSString *name in @[UIApplicationDidBecomeActiveNotification, UIApplicationDidEnterBackgroundNotification]) {
            id token = [center addObserverForName:name object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *note) {
                [self emit:@{@"op": @"lifecycle", @"event": [note.name isEqualToString:UIApplicationDidBecomeActiveNotification] ? @"resume" : @"pause"}];
            }];
            [_observerTokens addObject:token];
        }
    }
    return self;
}

- (void)startPython {
    if (self.started) return;
    self.started = YES;
    if ([NSBundle.mainBundle.bundlePath.pathExtension isEqualToString:@"appex"]) {
        self.startupError = @"Plugins run in the main application only.";
        return;
    }
    NSString *root = [NSBundle.mainBundle.resourcePath stringByAppendingPathComponent:@"ExteraPython"];
    if (![NSFileManager.defaultManager fileExistsAtPath:[root stringByAppendingPathComponent:@"stdlib/encodings/__init__.py"]]) {
        self.startupError = @"Python resources are missing from this build.";
        return;
    }
    if (Py_IsInitialized()) {
        self.startupError = @"Another Python interpreter already exists in this process.";
        return;
    }
    if (PyImport_AppendInittab("_extera_native", PyInit_extera_native) < 0) {
        self.startupError = @"Could not register the native Python bridge.";
        return;
    }
    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);
    config.write_bytecode = 0;
    config.install_signal_handlers = 0;
    config.site_import = 0;
    config.module_search_paths_set = 1;
    PyStatus status = PyConfig_SetBytesString(&config, &config.home, root.UTF8String);
    for (NSString *part in @[@"stdlib", @"lib-dynload", @"sdk"]) {
        if (PyStatus_Exception(status)) break;
        wchar_t *path = Py_DecodeLocale([[root stringByAppendingPathComponent:part] UTF8String], NULL);
        if (path) {
            status = PyWideStringList_Append(&config.module_search_paths, path);
            PyMem_RawFree(path);
        } else {
            status = PyStatus_Error("Cannot decode Python resource path");
        }
    }
    if (!PyStatus_Exception(status)) status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) {
        self.startupError = status.err_msg ? [NSString stringWithUTF8String:status.err_msg] : @"Python initialization failed.";
        PyConfig_Clear(&config);
        return;
    }
    PyConfig_Clear(&config);
    PyObject *module = PyImport_ImportModule("extera_runtime");
    if (module) {
        NSString *documents = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
        NSString *support = [[NSSearchPathForDirectoriesInDomains(NSApplicationSupportDirectory, NSUserDomainMask, YES) firstObject] stringByAppendingPathComponent:@"ExteraPlugins"];
        PyObject *initialized = PyObject_CallMethod(module, "initialize", "ss", documents.UTF8String, support.UTF8String);
        if (initialized) {
            self.dispatcher = PyObject_GetAttrString(module, "dispatch");
            Py_DECREF(initialized);
        }
        Py_DECREF(module);
    }
    if (!self.dispatcher) {
        PyErr_Print();
        self.startupError = @"Python plugin SDK failed to initialize. See the device console.";
    }
    // Py_InitializeFromConfig acquired the GIL. Release it so plugins' Python
    // worker threads and future calls through PyGILState_Ensure can run.
    PyEval_SaveThread();
}

- (NSDictionary *)performRequest:(NSDictionary *)request {
    [self startPython];
    if (self.startupError) return @{@"error": self.startupError};
    NSError *error = nil;
    NSData *encoded = [NSJSONSerialization dataWithJSONObject:request options:0 error:&error];
    if (!encoded) return @{@"error": error.localizedDescription ?: @"Invalid request"};
    NSString *json = [[NSString alloc] initWithData:encoded encoding:NSUTF8StringEncoding];
    PyGILState_STATE gil = PyGILState_Ensure();
    PyObject *result = PyObject_CallFunction(self.dispatcher, "s", json.UTF8String);
    NSDictionary *response = nil;
    if (result) {
        const char *text = PyUnicode_AsUTF8(result);
        if (text) {
            NSData *bytes = [[NSString stringWithUTF8String:text] dataUsingEncoding:NSUTF8StringEncoding];
            id object = [NSJSONSerialization JSONObjectWithData:bytes options:0 error:NULL];
            if ([object isKindOfClass:NSDictionary.class]) response = object;
        }
        Py_DECREF(result);
    }
    if (!response) PyErr_Print();
    PyGILState_Release(gil);
    if ([request[@"op"] isEqualToString:@"logs"] && response[@"lines"]) {
        @synchronized (self.nativeLogs) {
            NSMutableDictionary *combined = [response mutableCopy];
            combined[@"lines"] = [response[@"lines"] arrayByAddingObjectsFromArray:self.nativeLogs];
            response = combined;
        }
    }
    return response ?: @{@"error": @"Python did not return a valid response."};
}

- (NSDictionary<NSString *,id> *)request:(NSDictionary<NSString *,id> *)request {
    if (dispatch_get_specific(EPQueueKey)) return [self performRequest:request];
    __block NSDictionary *result;
    dispatch_sync(self.queue, ^{ result = [self performRequest:request]; });
    return result;
}

- (void)emit:(NSDictionary<NSString *,id> *)event {
    dispatch_async(self.queue, ^{ [self performRequest:event]; });
}

- (void)emitForeground:(NSDictionary<NSString *,id> *)event {
    dispatch_async(dispatch_get_main_queue(), ^{
        if (UIApplication.sharedApplication.applicationState == UIApplicationStateActive) [self emit:event];
    });
}

- (void)presentManagerForAccount:(int64_t)account {
    dispatch_async(dispatch_get_main_queue(), ^{
        EPPluginManagerController *manager = [[EPPluginManagerController alloc] initWithAccount:account];
        UINavigationController *navigation = [[UINavigationController alloc] initWithRootViewController:manager];
        [EPTopController() presentViewController:navigation animated:YES completion:nil];
    });
}

- (void)recordNativeError:(NSString *)error {
    if (!error) return;
    NSLog(@"[exteraGram Plugins] %@", error);
    @synchronized (self.nativeLogs) {
        [self.nativeLogs addObject:error];
        if (self.nativeLogs.count > 100) [self.nativeLogs removeObjectAtIndex:0];
    }
    [[NSNotificationCenter defaultCenter] postNotificationName:@"EPPluginNativeError" object:error];
}

- (void)nativeCommand:(NSDictionary *)command {
    NSString *name = command[@"command"];
    NSString *token = command[@"token"];
    if ([name isEqualToString:@"clipboard"]) {
        UIPasteboard.generalPasteboard.string = command[@"text"];
    } else if ([name isEqualToString:@"bulletin"]) {
        UIViewController *top = EPTopController();
        if (!top.view.window) return;
        UILabel *label = [[UILabel alloc] init];
        label.text = command[@"text"];
        label.numberOfLines = 0;
        label.textAlignment = NSTextAlignmentCenter;
        label.backgroundColor = UIColor.secondarySystemBackgroundColor;
        label.textColor = UIColor.labelColor;
        label.layer.cornerRadius = 14;
        label.clipsToBounds = YES;
        CGFloat width = MIN(top.view.bounds.size.width - 32, 420);
        CGSize size = [label sizeThatFits:CGSizeMake(width - 24, 200)];
        label.frame = CGRectMake((top.view.bounds.size.width - width) / 2, top.view.safeAreaInsets.top + 12, width, size.height + 24);
        [top.view addSubview:label];
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.0 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
            [UIView animateWithDuration:0.2 animations:^{ label.alpha = 0; } completion:^(BOOL finished) { [label removeFromSuperview]; }];
        });
    } else if ([name isEqualToString:@"pop_settings"]) {
        UIViewController *top = EPTopController();
        if ([top isKindOfClass:UINavigationController.class]) {
            UINavigationController *nav = (UINavigationController *)top;
            if ([nav.topViewController isKindOfClass:EPPluginSettingsController.class] && nav.viewControllers.count > 2) {
                [nav popViewControllerAnimated:YES];
            }
        }
    } else if ([name isEqualToString:@"audio_prepare"]) {
        NSString *path = command[@"path"];
        if (![path isKindOfClass:NSString.class] || ![token isKindOfClass:NSString.class]) return;
        NSString *documents = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject].stringByResolvingSymlinksInPath;
        NSString *resolved = path.stringByResolvingSymlinksInPath;
        if (![resolved hasPrefix:[documents stringByAppendingString:@"/"]]) {
            [self recordNativeError:@"Audio source must be imported into this application's Documents folder."];
            return;
        }
        if (self.players.count >= 128 && !self.players[token]) {
            [self recordNativeError:@"Too many audio players; disable and re-enable the plugin."];
            return;
        }
        NSError *error = nil;
        AVAudioPlayer *player = [[AVAudioPlayer alloc] initWithContentsOfURL:[NSURL fileURLWithPath:resolved] error:&error];
        if (player && [player prepareToPlay]) self.players[token] = player;
        else [self recordNativeError:error.localizedDescription ?: @"iOS cannot decode this audio format. Try WAV, MP3, M4A or AAC."];
    } else if ([name isEqualToString:@"audio_seek"]) {
        self.players[token].currentTime = [command[@"seconds"] doubleValue];
    } else if ([name isEqualToString:@"audio_play"]) {
        if (![self.players[token] play]) [self recordNativeError:@"Could not play the selected sound."];
    } else if ([name isEqualToString:@"audio_release"]) {
        [self.players[token] stop];
        [self.players removeObjectForKey:token];
    }
}
@end
