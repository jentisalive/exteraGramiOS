#import <UIKit/UIKit.h>

@interface EPPluginManagerController : UITableViewController <UIDocumentPickerDelegate>
- (instancetype)initWithAccount:(int64_t)account;
@end

@interface EPPluginSettingsController : UITableViewController
- (instancetype)initWithPlugin:(NSString *)pluginId account:(int64_t)account rows:(NSArray *)rows;
@end
