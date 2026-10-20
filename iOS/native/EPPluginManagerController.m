#import "EPPluginManagerController.h"
#import "EPPluginHost.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

static void EPRequest(NSDictionary *request, void (^completion)(NSDictionary *)) {
    static dispatch_queue_t queue;
    static dispatch_once_t once;
    dispatch_once(&once, ^{ queue = dispatch_queue_create("app.exteragram.plugin-ui", DISPATCH_QUEUE_SERIAL); });
    dispatch_async(queue, ^{
        NSDictionary *response = [[EPPluginHost shared] request:request];
        dispatch_async(dispatch_get_main_queue(), ^{ completion(response); });
    });
}

static void EPAlert(UIViewController *controller, NSString *title, NSString *message) {
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:title message:message preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:@"OK" style:UIAlertActionStyleDefault handler:nil]];
    [controller presentViewController:alert animated:YES completion:nil];
}

@interface EPPluginManagerController ()
@property(nonatomic) int64_t account;
@property(nonatomic, strong) NSArray *plugins;
@property(nonatomic, strong) NSArray *menuItems;
@end

@implementation EPPluginManagerController
- (instancetype)initWithAccount:(int64_t)account {
    if ((self = [super initWithStyle:UITableViewStyleInsetGrouped])) {
        _account = account;
        _plugins = @[];
        _menuItems = @[];
        self.title = @"exteraGram Plugins";
        self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithBarButtonSystemItem:UIBarButtonSystemItemDone target:self action:@selector(close)];
    }
    return self;
}

- (void)close { [self dismissViewControllerAnimated:YES completion:nil]; }

- (void)viewWillAppear:(BOOL)animated {
    [super viewWillAppear:animated];
    [self reload];
}

- (void)reload {
    __weak typeof(self) weakSelf = self;
    EPRequest(@{@"op": @"list", @"account": @(self.account)}, ^(NSDictionary *response) {
        typeof(self) self = weakSelf;
        if (!self) return;
        if (response[@"error"]) {
            EPAlert(self, @"Plugin runtime", response[@"error"]);
            return;
        }
        self.plugins = response[@"plugins"] ?: @[];
        [self.tableView reloadData];
    });
    EPRequest(@{@"op": @"menus", @"menu": @"main", @"account": @(self.account)}, ^(NSDictionary *response) {
        weakSelf.menuItems = response[@"items"] ?: @[];
        [weakSelf.tableView reloadData];
    });
}

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return 4; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    if (section == 0) return 2;
    if (section == 1) return self.plugins.count;
    if (section == 2) return self.menuItems.count;
    return 1;
}
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    return @[@"Import", @"Installed plugins", @"Plugin actions", @"Diagnostics"][section];
}
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (section == 0) return @"Import a .plugin file, then enable it below. Plugins execute Python with access to your app data; enable only plugins you trust. Import audio files here for Sound Actions.";
    if (section == 1 && !self.plugins.count) return @"No plugins installed.";
    if (section == 2) return @"Main-menu actions from enabled plugins appear here. Chat actions appear in the chat's More menu.";
    return nil;
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.numberOfLines = 0;
    cell.detailTextLabel.numberOfLines = 0;
    if (indexPath.section == 0) {
        cell.textLabel.text = indexPath.row == 0 ? @"Import plugin or audio…" : @"Open app folder";
        cell.imageView.image = [UIImage systemImageNamed:indexPath.row == 0 ? @"square.and.arrow.down" : @"folder"];
    } else if (indexPath.section == 1) {
        NSDictionary *plugin = self.plugins[indexPath.row];
        cell.textLabel.text = plugin[@"name"];
        cell.detailTextLabel.text = [plugin[@"error"] length] ? plugin[@"error"] : [NSString stringWithFormat:@"%@ · %@", plugin[@"version"] ?: @"", plugin[@"description"] ?: @""];
        UISwitch *toggle = [[UISwitch alloc] init];
        toggle.on = [plugin[@"enabled"] boolValue];
        toggle.tag = indexPath.row;
        [toggle addTarget:self action:@selector(togglePlugin:) forControlEvents:UIControlEventValueChanged];
        cell.accessoryView = toggle;
    } else if (indexPath.section == 2) {
        cell.textLabel.text = self.menuItems[indexPath.row][@"text"];
        cell.detailTextLabel.text = self.menuItems[indexPath.row][@"subtext"];
    } else {
        cell.textLabel.text = @"Runtime logs";
        cell.imageView.image = [UIImage systemImageNamed:@"doc.text.magnifyingglass"];
    }
    return cell;
}

- (void)togglePlugin:(UISwitch *)toggle {
    if (toggle.tag >= (NSInteger)self.plugins.count) return;
    NSDictionary *plugin = self.plugins[toggle.tag];
    toggle.enabled = NO;
    EPRequest(@{@"op": @"enable", @"id": plugin[@"id"], @"enabled": @(toggle.on), @"account": @(self.account)}, ^(NSDictionary *response) {
        toggle.enabled = YES;
        if (response[@"error"]) EPAlert(self, @"Plugin could not be enabled", response[@"error"]);
        [self reload];
    });
}

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if (indexPath.section == 0 && indexPath.row == 0) {
        UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[UTTypeData, UTTypeAudio] asCopy:YES];
        picker.delegate = self;
        [self presentViewController:picker animated:YES completion:nil];
    } else if (indexPath.section == 0) {
        NSString *documents = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
        NSURLComponents *components = [NSURLComponents componentsWithURL:[NSURL fileURLWithPath:documents isDirectory:YES] resolvingAgainstBaseURL:NO];
        components.scheme = @"shareddocuments";
        [UIApplication.sharedApplication openURL:components.URL options:@{} completionHandler:^(BOOL success) {
            if (!success) EPAlert(self, @"App folder", @"Open Files → On My iPhone → exteraGram. Audio files go in Audio; imported plugins are in Plugins.");
        }];
    } else if (indexPath.section == 1) {
        NSDictionary *plugin = self.plugins[indexPath.row];
        EPRequest(@{@"op": @"settings", @"id": plugin[@"id"], @"account": @(self.account)}, ^(NSDictionary *response) {
            if (response[@"error"]) { EPAlert(self, @"Plugin settings", response[@"error"]); return; }
            EPPluginSettingsController *settings = [[EPPluginSettingsController alloc] initWithPlugin:plugin[@"id"] account:self.account rows:response[@"rows"] ?: @[]];
            settings.title = plugin[@"name"];
            [self.navigationController pushViewController:settings animated:YES];
        });
    } else if (indexPath.section == 2) {
        NSDictionary *item = self.menuItems[indexPath.row];
        EPRequest(@{@"op": @"menu_click", @"item": item[@"id"], @"account": @(self.account), @"context": @{}}, ^(NSDictionary *response) {
            if (response[@"error"]) EPAlert(self, @"Plugin action", response[@"error"]);
            [self reload];
        });
    } else {
        EPRequest(@{@"op": @"logs"}, ^(NSDictionary *response) {
            UIViewController *controller = [[UIViewController alloc] init];
            controller.title = @"Runtime logs";
            UITextView *text = [[UITextView alloc] init];
            text.editable = NO;
            text.font = [UIFont monospacedSystemFontOfSize:12 weight:UIFontWeightRegular];
            text.text = response[@"error"] ?: [response[@"lines"] componentsJoinedByString:@"\n"];
            controller.view = text;
            [self.navigationController pushViewController:controller animated:YES];
        });
    }
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
    NSURL *url = urls.firstObject;
    if (!url) return;
    BOOL scoped = [url startAccessingSecurityScopedResource];
    if ([url.pathExtension.lowercaseString isEqualToString:@"plugin"]) {
        // The asynchronous request must finish before relinquishing the file URL.
        EPRequest(@{@"op": @"import", @"path": url.path, @"account": @(self.account)}, ^(NSDictionary *response) {
            if (scoped) [url stopAccessingSecurityScopedResource];
            if (response[@"error"]) EPAlert(self, @"Import failed", response[@"error"]);
            [self reload];
        });
    } else {
        NSSet *supported = [NSSet setWithArray:@[@"mp3", @"m4a", @"wav", @"aac", @"aiff", @"aif", @"caf", @"flac", @"ogg", @"oga", @"opus", @"mp4", @"3gp", @"amr"]];
        if (![supported containsObject:url.pathExtension.lowercaseString]) {
            if (scoped) [url stopAccessingSecurityScopedResource];
            EPAlert(self, @"Unsupported file", @"Choose a .plugin file or an audio file.");
            return;
        }
        NSString *documents = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
        NSString *directory = [documents stringByAppendingPathComponent:@"Audio"];
        [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:NULL];
        NSString *base = url.lastPathComponent.stringByDeletingPathExtension;
        NSString *destination = [directory stringByAppendingPathComponent:url.lastPathComponent];
        for (NSInteger index = 2; [NSFileManager.defaultManager fileExistsAtPath:destination]; index++) {
            destination = [directory stringByAppendingPathComponent:[NSString stringWithFormat:@"%@ (%ld).%@", base, (long)index, url.pathExtension]];
        }
        NSError *error = nil;
        [NSFileManager.defaultManager copyItemAtURL:url toURL:[NSURL fileURLWithPath:destination] error:&error];
        if (scoped) [url stopAccessingSecurityScopedResource];
        EPAlert(self, error ? @"Import failed" : @"Audio imported", error.localizedDescription ?: @"Select this file in your plugin's sound settings. iOS playback support depends on the audio codec.");
    }
}

- (BOOL)tableView:(UITableView *)tableView canEditRowAtIndexPath:(NSIndexPath *)indexPath { return indexPath.section == 1; }
- (void)tableView:(UITableView *)tableView commitEditingStyle:(UITableViewCellEditingStyle)style forRowAtIndexPath:(NSIndexPath *)indexPath {
    if (style != UITableViewCellEditingStyleDelete || indexPath.section != 1) return;
    NSDictionary *plugin = self.plugins[indexPath.row];
    EPRequest(@{@"op": @"remove", @"id": plugin[@"id"], @"account": @(self.account)}, ^(NSDictionary *response) {
        if (response[@"error"]) EPAlert(self, @"Remove failed", response[@"error"]);
        [self reload];
    });
}
@end

@interface EPPluginSettingsController ()
@property(nonatomic, copy) NSString *pluginId;
@property(nonatomic) int64_t account;
@property(nonatomic, strong) NSArray *rows;
@end

@implementation EPPluginSettingsController
- (instancetype)initWithPlugin:(NSString *)pluginId account:(int64_t)account rows:(NSArray *)rows {
    if ((self = [super initWithStyle:UITableViewStyleInsetGrouped])) {
        _pluginId = pluginId;
        _account = account;
        _rows = rows;
    }
    return self;
}

- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return self.rows.count; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    NSDictionary *row = self.rows[indexPath.row];
    UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
    cell.textLabel.text = row[@"text"];
    cell.detailTextLabel.text = row[@"subtext"];
    cell.textLabel.numberOfLines = 0;
    cell.detailTextLabel.numberOfLines = 0;
    if ([row[@"kind"] isEqualToString:@"header"]) {
        cell.textLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleHeadline];
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
    } else if ([row[@"kind"] isEqualToString:@"divider"]) {
        cell.selectionStyle = UITableViewCellSelectionStyleNone;
    } else if ([row[@"kind"] isEqualToString:@"switch"]) {
        UISwitch *toggle = [[UISwitch alloc] init];
        toggle.on = [row[@"value"] boolValue];
        toggle.tag = indexPath.row;
        [toggle addTarget:self action:@selector(toggleSetting:) forControlEvents:UIControlEventValueChanged];
        cell.accessoryView = toggle;
    } else if (row[@"callback"]) {
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
    }
    return cell;
}

- (void)refreshRoot {
    EPRequest(@{@"op": @"settings", @"id": self.pluginId, @"account": @(self.account)}, ^(NSDictionary *response) {
        if (response[@"error"]) { EPAlert(self, @"Plugin settings", response[@"error"]); return; }
        self.rows = response[@"rows"] ?: @[];
        [self.tableView reloadData];
    });
}

- (void)viewWillAppear:(BOOL)animated {
    [super viewWillAppear:animated];
    if (self.navigationController.viewControllers.count == 2) [self refreshRoot];
}

- (void)toggleSetting:(UISwitch *)toggle {
    NSDictionary *row = self.rows[toggle.tag];
    NSMutableDictionary *request = [@{@"op": row[@"on_change"] ? @"callback" : @"setting", @"id": self.pluginId, @"account": @(self.account), @"key": row[@"key"], @"value": @(toggle.on)} mutableCopy];
    if (row[@"on_change"]) request[@"callback"] = row[@"on_change"];
    toggle.enabled = NO;
    EPRequest(request, ^(NSDictionary *response) {
        toggle.enabled = YES;
        if (response[@"error"]) { toggle.on = !toggle.on; EPAlert(self, @"Setting failed", response[@"error"]); }
    });
}

- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    NSDictionary *row = self.rows[indexPath.row];
    if (!row[@"callback"]) return;
    EPRequest(@{@"op": @"callback", @"id": self.pluginId, @"callback": row[@"callback"], @"account": @(self.account)}, ^(NSDictionary *response) {
        if (response[@"error"]) { EPAlert(self, @"Plugin action failed", response[@"error"]); return; }
        if (response[@"rows"]) {
            EPPluginSettingsController *page = [[EPPluginSettingsController alloc] initWithPlugin:self.pluginId account:self.account rows:response[@"rows"]];
            page.title = row[@"text"];
            [self.navigationController pushViewController:page animated:YES];
        }
    });
}
@end
