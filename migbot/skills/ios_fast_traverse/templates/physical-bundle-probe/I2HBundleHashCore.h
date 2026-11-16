//
//  I2HBundleHashCore.h
//
//  Foundation-only bundle hashing core matching ios_evidence_protocol.py source_identity().
//  Shared between iOS probe (UIKit) and macOS CLI harness (Foundation).
//

#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Result of bundle hash computation
@interface I2HBundleHashResult : NSObject

@property (nonatomic, readonly) BOOL success;
@property (nonatomic, readonly, nullable) NSString *sha256Hex;
@property (nonatomic, readonly, nullable) NSError *error;

+ (instancetype)successWithHash:(NSString *)sha256Hex;
+ (instancetype)failureWithError:(NSError *)error;

@end

/// Foundation-only core implementing EXACT algorithm from ios_evidence_protocol.py source_identity()
@interface I2HBundleHashCore : NSObject

/// Compute bundle hash: sorted relative POSIX paths + NUL + file bytes + NUL
/// Excludes symlinks and EXCLUDED_PARTS (.git, .build, DerivedData, build, dist, node_modules)
/// Returns result with sha256Hex on success or error on failure (fail-closed)
+ (I2HBundleHashResult *)computeHashAtURL:(NSURL *)bundleURL;

@end

NS_ASSUME_NONNULL_END
