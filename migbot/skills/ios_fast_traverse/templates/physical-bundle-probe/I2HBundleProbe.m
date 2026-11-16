//
//  I2HBundleProbe.m
//
//  DEBUG-only bundle integrity probe for physical device test evidence binding.
//

#import "I2HBundleProbe.h"
#import "I2HBundleHashCore.h"
#import <UIKit/UIKit.h>
#import <CommonCrypto/CommonDigest.h>

@implementation I2HBundleProbe

+ (void)load {
#if DEBUG
    // Auto-register observer on class load - no app code modification needed
    [[NSNotificationCenter defaultCenter] addObserverForName:UIApplicationDidBecomeActiveNotification
                                                      object:nil
                                                       queue:[NSOperationQueue mainQueue]
                                                  usingBlock:^(NSNotification *note) {
        [self handleDidBecomeActive];
    }];
#endif
}

+ (void)handleDidBecomeActive {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        // Only execute probe once per app launch, on first foreground activation
        NSArray<NSString *> *arguments = [[NSProcessInfo processInfo] arguments];
        NSString *challenge = nil;

        for (NSUInteger i = 0; i < arguments.count - 1; i++) {
            if ([arguments[i] isEqualToString:@"-I2HBundleProbeChallenge"]) {
                challenge = arguments[i + 1];
                break;
            }
        }

        if (challenge == nil || challenge.length == 0) {
            return; // No challenge provided, probe not requested
        }

        // Probe requested - execute on background queue to avoid blocking main thread
        dispatch_async(dispatch_get_global_queue(DISPATCH_QUEUE_PRIORITY_DEFAULT, 0), ^{
            [self executeProbWithChallenge:challenge];
        });
    });
}

+ (void)executeProbWithChallenge:(NSString *)challenge {
    @autoreleasepool {
        NSMutableDictionary *receipt = [NSMutableDictionary dictionary];

        // Record metadata
        receipt[@"probe_type"] = @"installed_bundle_hash";
        receipt[@"instrumented_variant"] = @"DEBUG_source_test_only";
        receipt[@"challenge"] = challenge;

        // Record timestamps at probe start
        NSDate *probeStartTime = [NSDate date];
        receipt[@"probe_start_utc"] = [self iso8601Timestamp:probeStartTime];
        receipt[@"pid"] = @([[NSProcessInfo processInfo] processIdentifier]);

        // Bundle metadata
        NSBundle *mainBundle = [NSBundle mainBundle];
        receipt[@"bundle_id"] = [mainBundle bundleIdentifier] ?: @"unknown";
        receipt[@"version"] = [mainBundle objectForInfoDictionaryKey:@"CFBundleShortVersionString"] ?: @"unknown";
        receipt[@"build"] = [mainBundle objectForInfoDictionaryKey:@"CFBundleVersion"] ?: @"unknown";

        // Verify foreground state at probe start
        __block UIApplicationState startState = UIApplicationStateBackground;
        dispatch_sync(dispatch_get_main_queue(), ^{
            startState = [[UIApplication sharedApplication] applicationState];
        });

        if (startState != UIApplicationStateActive) {
            // Not in foreground - write error receipt
            receipt[@"error"] = @"probe_not_in_foreground_at_start";
            receipt[@"application_state_at_start"] = @(startState);
            [self writeErrorReceipt:receipt];
            return;
        }

        receipt[@"foreground_at_probe_start"] = @YES;
        receipt[@"application_state_at_start"] = @(startState);

        // Compute installed bundle hash using shared core (matches ios_evidence_protocol.py)
        NSURL *bundleURL = [mainBundle bundleURL];
        I2HBundleHashResult *hashResult = [I2HBundleHashCore computeHashAtURL:bundleURL];

        if (!hashResult.success) {
            // Hash computation failed - write error receipt
            receipt[@"error"] = @"bundle_hash_computation_failed";
            receipt[@"error_detail"] = [hashResult.error localizedDescription];
            [self writeErrorReceipt:receipt];
            return;
        }

        receipt[@"installed_bundle_sha256"] = hashResult.sha256Hex;
        receipt[@"bundle_path"] = [bundleURL path] ?: @"unknown";

        // Record timestamp at probe end
        NSDate *probeEndTime = [NSDate date];
        receipt[@"probe_end_utc"] = [self iso8601Timestamp:probeEndTime];
        receipt[@"probe_duration_seconds"] = @([probeEndTime timeIntervalSinceDate:probeStartTime]);

        // Verify foreground state at probe end
        __block UIApplicationState endState = UIApplicationStateBackground;
        dispatch_sync(dispatch_get_main_queue(), ^{
            endState = [[UIApplication sharedApplication] applicationState];
        });

        if (endState != UIApplicationStateActive) {
            // Lost foreground during probe - write error receipt
            receipt[@"error"] = @"lost_foreground_during_probe";
            receipt[@"application_state_at_end"] = @(endState);
            [self writeErrorReceipt:receipt];
            return;
        }

        receipt[@"foreground_at_probe_end"] = @YES;
        receipt[@"application_state_at_end"] = @(endState);

        // Write successful receipt to app's data container (Documents directory)
        [self writeSuccessfulReceipt:receipt];
    }
}

+ (void)writeSuccessfulReceipt:(NSDictionary *)receipt {
    NSString *documentsPath = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
    NSString *receiptPath = [documentsPath stringByAppendingPathComponent:@"i2h_bundle_probe_receipt.json"];

    NSError *error = nil;
    NSData *jsonData = [NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingPrettyPrinted error:&error];
    if (jsonData && !error) {
        [jsonData writeToFile:receiptPath atomically:YES];
        NSLog(@"[I2HBundleProbe] SUCCESS: Receipt written to: %@", receiptPath);
    } else {
        NSLog(@"[I2HBundleProbe] ERROR: Failed to write receipt: %@", error);
    }
}

+ (void)writeErrorReceipt:(NSDictionary *)receipt {
    NSString *documentsPath = [NSSearchPathForDirectoriesInDomains(NSDocumentDirectory, NSUserDomainMask, YES) firstObject];
    NSString *receiptPath = [documentsPath stringByAppendingPathComponent:@"i2h_bundle_probe_receipt_error.json"];

    NSError *error = nil;
    NSData *jsonData = [NSJSONSerialization dataWithJSONObject:receipt options:NSJSONWritingPrettyPrinted error:&error];
    if (jsonData && !error) {
        [jsonData writeToFile:receiptPath atomically:YES];
        NSLog(@"[I2HBundleProbe] ERROR RECEIPT: %@", receiptPath);
    }
}

+ (NSString *)iso8601Timestamp:(NSDate *)date {
    NSDateFormatter *formatter = [[NSDateFormatter alloc] init];
    formatter.dateFormat = @"yyyy-MM-dd'T'HH:mm:ss.SSS'Z'";
    formatter.timeZone = [NSTimeZone timeZoneWithName:@"UTC"];
    return [formatter stringFromDate:date];
}

@end
