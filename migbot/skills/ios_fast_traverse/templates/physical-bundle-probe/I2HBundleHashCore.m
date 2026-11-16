//
//  I2HBundleHashCore.m
//
//  Foundation-only bundle hashing core matching ios_evidence_protocol.py source_identity().
//

#import "I2HBundleHashCore.h"
#import <CommonCrypto/CommonDigest.h>

@implementation I2HBundleHashResult

+ (instancetype)successWithHash:(NSString *)sha256Hex {
    I2HBundleHashResult *result = [[I2HBundleHashResult alloc] init];
    result->_success = YES;
    result->_sha256Hex = [sha256Hex copy];
    result->_error = nil;
    return result;
}

+ (instancetype)failureWithError:(NSError *)error {
    I2HBundleHashResult *result = [[I2HBundleHashResult alloc] init];
    result->_success = NO;
    result->_sha256Hex = nil;
    result->_error = error;
    return result;
}

@end

@implementation I2HBundleHashCore

+ (I2HBundleHashResult *)computeHashAtURL:(NSURL *)bundleURL {
    NSFileManager *fileManager = [NSFileManager defaultManager];

    // Resolve symlinks in bundle URL to match Python's Path.resolve() semantics
    // This ensures /var and /private/var map to the same canonical path
    NSError *resolveError = nil;
    NSURL *resolvedBundleURL = [bundleURL URLByResolvingSymlinksInPath];
    if (!resolvedBundleURL) {
        resolvedBundleURL = bundleURL;
    }

    NSString *bundlePath = [resolvedBundleURL path];

    if (!bundlePath || ![fileManager fileExistsAtPath:bundlePath]) {
        NSError *error = [NSError errorWithDomain:@"I2HBundleHashCore"
                                            code:-1
                                        userInfo:@{NSLocalizedDescriptionKey: @"Bundle path does not exist"}];
        return [I2HBundleHashResult failureWithError:error];
    }

    // EXCLUDED_PARTS from ios_evidence_protocol.py
    NSSet<NSString *> *excludedParts = [NSSet setWithArray:@[@".git", @".build", @"DerivedData", @"build", @"dist", @"node_modules"]];

    // Collect all files recursively, excluding symlinks and excluded parts
    // Store both relative path (for hashing) and absolute path (for reading)
    NSMutableArray<NSDictionary *> *files = [NSMutableArray array];
    __block NSError *enumerationError = nil;

    NSDirectoryEnumerator *enumerator = [fileManager enumeratorAtURL:resolvedBundleURL
                                          includingPropertiesForKeys:@[NSURLIsSymbolicLinkKey, NSURLIsDirectoryKey, NSURLIsRegularFileKey]
                                                             options:0
                                                        errorHandler:^BOOL(NSURL *url, NSError *error) {
        // Enumeration error - fail closed
        enumerationError = error;
        return NO; // Stop enumeration
    }];

    for (NSURL *fileURL in enumerator) {
        if (enumerationError != nil) {
            return [I2HBundleHashResult failureWithError:enumerationError];
        }

        NSNumber *isSymlink = nil;
        NSNumber *isDirectory = nil;
        NSNumber *isRegularFile = nil;
        NSError *resourceError = nil;

        // Check symlink first before following resource checks
        if (![fileURL getResourceValue:&isSymlink forKey:NSURLIsSymbolicLinkKey error:&resourceError]) {
            return [I2HBundleHashResult failureWithError:resourceError];
        }

        // Skip symlinks (Python: path.is_symlink())
        if ([isSymlink boolValue]) {
            continue;
        }

        if (![fileURL getResourceValue:&isDirectory forKey:NSURLIsDirectoryKey error:&resourceError]) {
            return [I2HBundleHashResult failureWithError:resourceError];
        }

        if (![fileURL getResourceValue:&isRegularFile forKey:NSURLIsRegularFileKey error:&resourceError]) {
            return [I2HBundleHashResult failureWithError:resourceError];
        }

        // Only hash regular files (Python: path.is_file() returns True only for regular files)
        // Skip directories, symlinks (already checked), FIFOs, sockets, and other non-regular files
        if ([isDirectory boolValue] || ![isRegularFile boolValue]) {
            continue;
        }

        // Get relative path and check for excluded parts
        // Need to handle /private/tmp -> /tmp aliasing without normalizing Unicode
        // Split into parent directory (which we standardize) and filename (which we preserve)
        NSURL *parentURL = [fileURL URLByDeletingLastPathComponent];
        NSString *filename = [fileURL lastPathComponent];
        NSString *standardizedParent = [[parentURL URLByStandardizingPath] path];
        NSString *absolutePath = [standardizedParent stringByAppendingPathComponent:filename];

        // Compute relative path robustly
        NSString *relativePath = nil;
        if ([absolutePath hasPrefix:bundlePath]) {
            relativePath = [absolutePath substringFromIndex:bundlePath.length];
            if ([relativePath hasPrefix:@"/"]) {
                relativePath = [relativePath substringFromIndex:1];
            }
        } else {
            // Path doesn't start with bundle path - should not happen with proper enumeration
            // but handle defensively
            NSError *error = [NSError errorWithDomain:@"I2HBundleHashCore"
                                                code:-1
                                            userInfo:@{NSLocalizedDescriptionKey: [NSString stringWithFormat:@"File path outside bundle: %@", absolutePath]}];
            return [I2HBundleHashResult failureWithError:error];
        }

        // Check if any path component is in excluded parts
        // Python: any(part in EXCLUDED_PARTS for part in path.relative_to(root).parts)
        NSArray<NSString *> *pathComponents = [relativePath pathComponents];
        BOOL shouldExclude = NO;
        for (NSString *component in pathComponents) {
            if ([excludedParts containsObject:component]) {
                shouldExclude = YES;
                break;
            }
        }

        if (!shouldExclude) {
            [files addObject:@{@"relative": relativePath, @"absolute": absolutePath}];
        }
    }

    // Check for enumeration error after loop completion
    if (enumerationError != nil) {
        return [I2HBundleHashResult failureWithError:enumerationError];
    }

    // Sort by relative paths using UTF-8 byte-wise comparison (matching Python sorted())
    [files sortUsingComparator:^NSComparisonResult(NSDictionary *file1, NSDictionary *file2) {
        NSString *path1 = file1[@"relative"];
        NSString *path2 = file2[@"relative"];
        // Compare UTF-8 encoded bytes directly
        NSData *data1 = [path1 dataUsingEncoding:NSUTF8StringEncoding];
        NSData *data2 = [path2 dataUsingEncoding:NSUTF8StringEncoding];

        NSUInteger len1 = [data1 length];
        NSUInteger len2 = [data2 length];
        NSUInteger minLen = MIN(len1, len2);

        const unsigned char *bytes1 = [data1 bytes];
        const unsigned char *bytes2 = [data2 bytes];

        int cmp = memcmp(bytes1, bytes2, minLen);
        if (cmp != 0) {
            return cmp < 0 ? NSOrderedAscending : NSOrderedDescending;
        }

        // If prefixes match, shorter string comes first
        if (len1 < len2) return NSOrderedAscending;
        if (len1 > len2) return NSOrderedDescending;
        return NSOrderedSame;
    }];

    // Compute hash: relative_posix_path + NUL + file_bytes + NUL
    CC_SHA256_CTX ctx;
    CC_SHA256_Init(&ctx);

    for (NSDictionary *file in files) {
        NSString *relativePath = file[@"relative"];
        NSString *absolutePath = file[@"absolute"];

        // Convert to POSIX path - Python: path.relative_to(root).as_posix()
        NSString *posixPath = relativePath;

        // Update hash with path (UTF-8 encoded) + NUL
        const char *pathBytes = [posixPath UTF8String];
        CC_SHA256_Update(&ctx, pathBytes, (CC_LONG)strlen(pathBytes));
        CC_SHA256_Update(&ctx, "\0", 1);

        // Read file bytes using stored absolute path
        NSError *readError = nil;
        NSData *fileData = [NSData dataWithContentsOfFile:absolutePath options:0 error:&readError];

        if (readError != nil || fileData == nil) {
            NSError *error = readError ?: [NSError errorWithDomain:@"I2HBundleHashCore"
                                                              code:-1
                                                          userInfo:@{NSLocalizedDescriptionKey: [NSString stringWithFormat:@"Failed to read file: %@", relativePath]}];
            return [I2HBundleHashResult failureWithError:error];
        }

        // Update hash with file bytes + NUL
        CC_SHA256_Update(&ctx, [fileData bytes], (CC_LONG)[fileData length]);
        CC_SHA256_Update(&ctx, "\0", 1);
    }

    // Finalize hash
    unsigned char digest[CC_SHA256_DIGEST_LENGTH];
    CC_SHA256_Final(digest, &ctx);

    // Convert to lowercase hex string (matching Python hexdigest())
    NSMutableString *hexString = [NSMutableString stringWithCapacity:CC_SHA256_DIGEST_LENGTH * 2];
    for (int i = 0; i < CC_SHA256_DIGEST_LENGTH; i++) {
        [hexString appendFormat:@"%02x", digest[i]];
    }

    return [I2HBundleHashResult successWithHash:hexString];
}

@end
