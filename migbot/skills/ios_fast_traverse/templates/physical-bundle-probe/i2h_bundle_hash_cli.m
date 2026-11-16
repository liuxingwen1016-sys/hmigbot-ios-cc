//
//  i2h_bundle_hash_cli.m
//
//  macOS Foundation CLI harness for I2HBundleHashCore validation.
//

#import <Foundation/Foundation.h>
#import "I2HBundleHashCore.h"

int main(int argc, const char * argv[]) {
    @autoreleasepool {
        if (argc != 2) {
            fprintf(stderr, "Usage: %s <bundle_path>\n", argv[0]);
            return 1;
        }

        NSString *bundlePath = [NSString stringWithUTF8String:argv[1]];
        NSURL *bundleURL = [NSURL fileURLWithPath:bundlePath];

        I2HBundleHashResult *result = [I2HBundleHashCore computeHashAtURL:bundleURL];

        if (result.success) {
            printf("%s\n", [result.sha256Hex UTF8String]);
            return 0;
        } else {
            fprintf(stderr, "ERROR: %s\n", [[result.error localizedDescription] UTF8String]);
            return 2;
        }
    }
    return 0;
}
