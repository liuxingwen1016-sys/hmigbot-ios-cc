---
name: ios2hmos_resources_convert
description: Convert iOS project resources to HarmonyOS project resources. Use this skill when the user wants to migrate, convert, or transfer resource files (strings, colors, dimensions, images, icons, etc.) from an iOS project to a HarmonyOS project. Also trigger when the user mentions iOS-to-HarmonyOS migration involving Assets.xcassets, Localizable.strings, Info.plist resources, or resource format conversion (plist/strings to JSON). Also trigger for SF Symbols icon usage, icon display issues (blank/invisible/wrong size), or icon mapping from iOS source code. Even partial mentions like "icon display broken", "SF Symbol not showing", "image size wrong", "migrate iOS icons" should trigger this skill.
type: domain
domain: migration
tags: [migration, resources, ios, assets]
---

# iOS to HarmonyOS Resource Converter

## Spec-only static facts

When called by i2h-spec with ui_facts_policy=static-v1, this skill's `extract_static_resource_facts.py` runs in a restricted mode:
- No write operations (spec is read-only)
- Output goes to `spec/baseline/resource-inventory.json` only
- No actual conversion, only cataloging

The script scans Assets.xcassets, Localizable.strings files, and Info.plist to produce a structured inventory of all resources declared in the iOS project.

## Prerequisites

- Python 3.8+ with `pillow` for image processing
- iOS project source directory with Assets.xcassets
- HarmonyOS project target directory (may be empty initially)
- For SVG icons: `librsvg` or equivalent for rasterization (optional)

## Step 1: Initialize Target Project (if needed)

Check if the target HarmonyOS project path exists and has the standard structure (`entry/src/main/resources/`).

If the path doesn't exist or is empty:

**Treat as fatal error** — resource conversion requires an existing HarmonyOS project. Instruct the user to create the project first using DevEco Studio or `arkts-project-scaffolder`.

### Step 2: Scan iOS Resources

Scan the iOS project's Assets.xcassets and localization files:

```bash
python3 scripts/scan_ios_resources.py \
  --ios-root /path/to/ios-project \
  --output /path/to/.codex/resource-inventory.json
```

The scanner catalogs:

1. **Images** (Assets.xcassets/\*/imageset/)
   - Image names
   - Resolutions (@1x, @2x, @3x)
   - Vector formats (PDF with "Preserve Vector Data")
   - Dark mode variants
   
2. **Colors** (Assets.xcassets/\*/colorset/)
   - Color names
   - Light/dark mode colors
   - RGB/RGBA values or system color references

3. **Strings** (Localizable.strings, InfoPlist.strings)
   - Localization keys
   - Translations per language (en, zh-Hans, etc.)
   - Format specifiers (%@, %d, etc.)

4. **App Icons** (AppIcon.appiconset)
   - All required sizes
   - Formats and resolutions

5. **Launch Screen** (LaunchScreen.storyboard or Assets.xcassets)
   - Launch image resources

6. **Fonts** (Custom fonts in project)
   - Font file names
   - Font family names from Info.plist

The inventory JSON format:

```json
{
  "images": [
    {
      "name": "icon_home",
      "variants": [
        {"scale": "1x", "filename": "icon_home.png"},
        {"scale": "2x", "filename": "icon_home@2x.png"},
        {"scale": "3x", "filename": "icon_home@3x.png"}
      ],
      "preserve_vector": false,
      "dark_mode": false
    }
  ],
  "colors": [
    {
      "name": "brandPrimary",
      "light": "#007AFF",
      "dark": "#0A84FF"
    }
  ],
  "strings": {
    "en": {
      "welcome_message": "Welcome",
      "login_button": "Sign In"
    },
    "zh-Hans": {
      "welcome_message": "欢迎",
      "login_button": "登录"
    }
  },
  "app_icons": {
    "sizes": ["20x20", "29x29", "40x40", "60x60", "76x76", "83.5x83.5", "1024x1024"]
  },
  "custom_fonts": [
    {
      "filename": "CustomFont-Regular.ttf",
      "family": "CustomFont"
    }
  ]
}
```

### Step 3: Convert Images

For each image in the inventory:

#### 3.1 Determine target resolution

iOS @2x and @3x images should be down-sampled to match HarmonyOS density buckets:

- @1x (mdpi baseline) → `base/media/` or `mdpi/media/`
- @2x (xhdpi ~2x) → `xhdpi/media/` or `xxhdpi/media/`
- @3x (xxhdpi ~3x) → `xxxhdpi/media/`

**Recommendation**: Use @2x as the base and place in `base/media/` for simplicity, unless pixel-perfect multi-density support is required.

#### 3.2 Copy and rename

iOS image name: `icon_home`
HarmonyOS file: `entry/src/main/resources/base/media/icon_home.png`

Rules:
- Convert image name to lowercase with underscores
- Remove iOS @ scale suffixes
- Preserve file extension (.png, .jpg)
- For PDF vector images marked "Preserve Vector Data", rasterize to PNG at @2x or @3x equivalent

#### 3.3 Handle dark mode variants

If dark mode variants exist in Assets.xcassets:
- Light variant → `base/media/icon_home.png`
- Dark variant → (HarmonyOS currently has limited dark mode resource support; consider embedding both in app and switching via `@State isDarkMode`)

Alternatively, if HarmonyOS adds dark mode qualifiers in future SDK versions, place dark variants in appropriate directories (e.g., `dark/media/`).

#### 3.4 SVG and vector images

iOS Assets.xcassets support PDF with "Preserve Vector Data" enabled. These are vector assets.

For HarmonyOS:
- SVG is supported in some components but not universally
- Safest approach: rasterize PDF to PNG at @2x or @3x (e.g., 48x48 for icons)
- Alternative: export SVG from Xcode and place in HarmonyOS resources, but verify rendering in target app

### Step 4: Convert Colors

For each color in Assets.xcassets:

#### 4.1 Extract RGB values

Parse `Contents.json` in each `*.colorset/` to get:
```json
{
  "colors": [
    {
      "color": {
        "color-space": "srgb",
        "components": {
          "red": "0.000",
          "green": "0.478",
          "blue": "1.000",
          "alpha": "1.000"
        }
      },
      "idiom": "universal"
    }
  ]
}
```

#### 4.2 Convert to HarmonyOS color.json

Output: `entry/src/main/resources/base/element/color.json`

```json
{
  "color": [
    {
      "name": "brand_primary",
      "value": "#007AFF"
    },
    {
      "name": "text_primary",
      "value": "#000000"
    }
  ]
}
```

Rules:
- Convert camelCase names to snake_case
- Convert RGB components (0.0-1.0) to hex (#RRGGBB or #RRGGBBAA)
- Merge light and dark mode colors if needed (or handle via app logic)

### Step 5: Convert Strings

For each localization language (e.g., `en.lproj/Localizable.strings`, `zh-Hans.lproj/Localizable.strings`):

#### 5.1 Parse .strings file

iOS format:
```
"welcome_message" = "Welcome";
"login_button" = "Sign In";
```

#### 5.2 Convert to HarmonyOS string.json

Output: `entry/src/main/resources/en_US/element/string.json` (for English)
Output: `entry/src/main/resources/zh_CN/element/string.json` (for Simplified Chinese)

```json
{
  "string": [
    {
      "name": "welcome_message",
      "value": "Welcome"
    },
    {
      "name": "login_button",
      "value": "Sign In"
    }
  ]
}
```

Language code mapping:
- `en.lproj` → `en_US/`
- `zh-Hans.lproj` → `zh_CN/`
- `zh-Hant.lproj` → `zh_TW/`
- `ja.lproj` → `ja_JP/`
- `ko.lproj` → `ko_KR/`
- `fr.lproj` → `fr_FR/`
- `de.lproj` → `de_DE/`
- `es.lproj` → `es_ES/`

#### 5.3 Handle format specifiers

iOS uses `%@`, `%d`, `%f` in strings:
```
"greeting" = "Hello, %@!";
```

HarmonyOS uses similar placeholders but verify behavior:
```json
{
  "name": "greeting",
  "value": "Hello, %s!"
}
```

Note: `%@` (iOS) generally maps to `%s` (HarmonyOS). Numeric placeholders remain `%d`, `%f`.

### Step 6: Convert App Icons

iOS AppIcon.appiconset contains multiple sizes (20x20, 29x29, 40x40, 60x60, 76x76, 83.5x83.5, 1024x1024).

HarmonyOS requires:
- `entry/src/main/resources/base/media/app_icon.png` (e.g., 512x512 or 1024x1024)

Extract the largest icon (1024x1024) and copy to HarmonyOS as `app_icon.png`. Also update `entry/src/main/module.json5`:

```json5
{
  "module": {
    "name": "entry",
    "icon": "$media:app_icon",
    ...
  }
}
```

### Step 7: Convert Launch Screen

If iOS uses LaunchScreen.storyboard with image assets:
- Extract the launch image from Assets.xcassets
- Copy to `entry/src/main/resources/base/media/launch_screen.png`

Update `entry/src/main/ets/pages/Index.ets` or create a splash page if needed.

If iOS uses dynamic launch screen (SwiftUI), migrate the UI logic separately using `swiftui-to-arkui`.

### Step 8: Convert Custom Fonts

If iOS project includes custom fonts (.ttf, .otf):

1. Copy font files to `entry/src/main/resources/rawfile/fonts/`
2. Register fonts in `entry/src/main/ets/pages/Index.ets` or app entry:

```typescript
// Register custom font
Font.register({
  familyName: 'CustomFont',
  familySrc: $rawfile('fonts/CustomFont-Regular.ttf')
})
```

3. Use in Text components:
```typescript
Text('Hello')
  .fontFamily('CustomFont')
```

### Step 9: Generate Conversion Report

After conversion, produce a summary report:

```markdown
# iOS → HarmonyOS Resource Conversion Report

## Summary
- Images converted: 45
- Colors converted: 12
- Strings converted: 89 keys × 3 languages
- App icons converted: 1
- Custom fonts converted: 2

## Image Conversion
| iOS Name | HarmonyOS Path | Resolution | Notes |
|----------|----------------|------------|-------|
| icon_home | base/media/icon_home.png | @2x → base | Converted from @2x |
| icon_profile | base/media/icon_profile.png | @3x → base | Down-sampled from @3x |

## Color Conversion
| iOS Name | HarmonyOS Name | Light | Dark |
|----------|----------------|-------|------|
| brandPrimary | brand_primary | #007AFF | #0A84FF |

## String Conversion
| Key | Languages | Status |
|-----|-----------|--------|
| welcome_message | en, zh-Hans, ja | ✅ Converted |
| login_button | en, zh-Hans | ✅ Converted |

## Warnings
- 3 SVG images rasterized to PNG (verify rendering)
- Dark mode color variants merged (app-side switching needed)
- 1 custom font requires manual registration in app entry

## Next Steps
1. Verify image rendering in HarmonyOS app
2. Test string localization switching
3. Register custom fonts in app entry
4. Verify app icon in launcher
```

## Error Handling

### Missing Assets.xcassets
If iOS project doesn't use Assets.xcassets (legacy project):
- Scan `Resources/` folder for direct image files
- Parse `Info.plist` for localized string file paths
- Warn user about manual resource organization

### Unsupported image formats
If iOS project uses HEIC or other formats not supported by HarmonyOS:
- Convert to PNG using `pillow`
- Log conversion in report

### Corrupt or missing @2x/@3x variants
If expected variants are missing:
- Use available highest resolution
- Down-sample or up-sample as needed
- Warn in report

## Quick Triage

Use this skill when the user asks:
- "Convert iOS resources to HarmonyOS"
- "Migrate Assets.xcassets to HarmonyOS"
- "How to move iOS images/colors/strings to HarmonyOS"
- "SF Symbol not showing in HarmonyOS"
- "Icons display blank after migration"

Do not use this skill for:
- Code migration (use `swiftui-to-arkui`)
- Business logic conversion
- Network or persistence layer migration
