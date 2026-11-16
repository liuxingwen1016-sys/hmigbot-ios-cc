//
//  I2HBundleProbe.h
//
//  DEBUG-only bundle integrity probe for physical device test evidence binding.
//  Activates on UIApplicationDidBecomeActive when explicit test launch args request it.
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// DEBUG-only probe that computes installed bundle hash on-device after foreground activation.
/// Matches exact algorithm from ios_evidence_protocol.py source_identity().
@interface I2HBundleProbe : NSObject

/// Auto-registers observer on load. No explicit call needed from app code.
/// Activates only on UIApplicationDidBecomeActive when test launch args provide challenge.
+ (void)load;

@end

NS_ASSUME_NONNULL_END
