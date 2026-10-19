#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
@interface EPPluginHost : NSObject
+ (instancetype)shared NS_SWIFT_NAME(shared());
- (NSDictionary<NSString *, id> *)request:(NSDictionary<NSString *, id> *)request NS_SWIFT_NAME(request(_:));
- (void)emit:(NSDictionary<NSString *, id> *)event NS_SWIFT_NAME(emit(_:));
- (void)emitForeground:(NSDictionary<NSString *, id> *)event NS_SWIFT_NAME(emitForeground(_:));
- (void)presentManagerForAccount:(int64_t)account NS_SWIFT_NAME(presentManager(account:));
@end
NS_ASSUME_NONNULL_END
