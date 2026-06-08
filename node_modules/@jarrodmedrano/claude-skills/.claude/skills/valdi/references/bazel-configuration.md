# Valdi Bazel Configuration

Detailed guide for configuring Bazel builds in Valdi projects.

## Project Structure

```
my_valdi_project/
├── MODULE.bazel           # Bazel module definition
├── WORKSPACE             # Workspace configuration
├── BUILD.bazel           # Root build file
├── .bazelrc              # Bazel configuration
├── .bazelversion         # Bazel version pinning
├── package.json          # Node dependencies
└── apps/
    └── my_app/
        ├── BUILD.bazel   # Application build
        └── src/
            └── valdi/
                └── my_module/
                    └── BUILD.bazel  # Module build
```

## Application BUILD.bazel

Complete example for a Valdi application:

```python
load("//bzl:valdi.bzl", "valdi_application", "valdi_exported_library")

# Main application target
valdi_application(
    name = "my_app",

    # App metadata
    title = "My Valdi Application",
    version = "1.0.0",

    # iOS configuration
    ios_bundle_id = "com.example.myapp",
    ios_device_families = ["iphone", "ipad"],
    ios_minimum_version = "14.0",

    # Android configuration
    android_package = "com.example.myapp",
    android_theme = "Theme.MyApp.Launch",
    android_app_icon = "app_icon",
    android_min_sdk = 24,
    android_target_sdk = 34,

    # macOS configuration (optional)
    macos_bundle_id = "com.example.myapp.macos",
    macos_minimum_version = "11.0",

    # Entry point
    root_component = "App@my_module/src/MyApp",

    # Assets
    assets = glob([
        "app_assets/**/*.png",
        "app_assets/**/*.jpg",
        "app_assets/**/*.jpeg",
        "app_assets/**/*.svg",
        "app_assets/**/*.webp",
        "app_assets/**/*.json",
    ]),

    # Dependencies
    deps = [
        "//apps/my_app/src/valdi/my_module",
    ],

    # Build visibility
    visibility = ["//visibility:public"],
)

# Exportable library for embedding in native apps
valdi_exported_library(
    name = "my_app_export",
    ios_bundle_id = "com.example.myapp.lib",
    bundle_name = "MyAppLib",
    deps = [
        "//apps/my_app/src/valdi/my_module",
    ],
    visibility = ["//visibility:public"],
)
```

## Module BUILD.bazel

Complete example for a Valdi module:

```python
load("//bzl:valdi.bzl", "valdi_module")

valdi_module(
    name = "my_module",

    # TypeScript/TSX source files
    srcs = glob([
        "src/**/*.ts",
        "src/**/*.tsx",
        "src/**/*.d.ts",
    ]) + [
        "tsconfig.json",
        ".terserrc.json",
    ],

    # Resource assets (images, etc.)
    assets = glob([
        "res/**/*.png",
        "res/**/*.jpg",
        "res/**/*.jpeg",
        "res/**/*.svg",
        "res/**/*.webp",
    ]),

    # Android platform configuration
    android = struct(
        class_path = "com.example.valdi.modules.my_module",
        native_deps = [
            "//apps/my_app/src/android:native_module",
        ],
        release = True,
    ),

    # iOS platform configuration
    ios = struct(
        module_name = "SCCMyModule",
        native_deps = [
            "//apps/my_app/src/ios:native_module",
        ],
        release = True,
    ),

    # C++ native dependencies
    native = struct(
        deps = [
            "//apps/my_app/src/cpp:native_module_cpp",
        ],
    ),

    # Valdi core dependencies
    deps = [
        "//src/valdi_modules/valdi_core",
        "//src/valdi_modules/valdi_tsx",
    ],

    visibility = ["//visibility:public"],
)
```

## Adding Additional Dependencies

### Using Valdi Modules

```python
deps = [
    # Core (always required)
    "//src/valdi_modules/valdi_core",
    "//src/valdi_modules/valdi_tsx",

    # Navigation
    "//src/valdi_modules/valdi_navigation",

    # HTTP client
    "//src/valdi_modules/valdi_http",

    # Storage
    "//src/valdi_modules/valdi_storage",

    # RxJS support
    "//src/valdi_modules/valdi_rxjs",

    # Protobuf
    "//src/valdi_modules/valdi_protobuf",
]
```

### Module-to-Module Dependencies

```python
# In feature_module/BUILD.bazel
valdi_module(
    name = "feature_module",
    srcs = glob(["src/**/*.ts", "src/**/*.tsx"]) + ["tsconfig.json"],
    deps = [
        "//src/valdi_modules/valdi_core",
        "//src/valdi_modules/valdi_tsx",
        # Depend on another module
        "//apps/my_app/src/valdi/shared_module",
    ],
)
```

## Native Dependencies

### C++ Module

```python
# In src/cpp/BUILD.bazel
cc_library(
    name = "native_module_cpp",
    srcs = [
        "native_module.cpp",
    ],
    hdrs = [
        "native_module.hpp",
    ],
    deps = [
        # Valdi C++ core
        "//valdi_core:valdi_core_cpp",
    ],
    visibility = ["//visibility:public"],
)
```

### iOS Module

```python
# In src/ios/BUILD.bazel
objc_library(
    name = "native_module",
    srcs = [
        "NativeModule.m",
    ],
    hdrs = [
        "NativeModule.h",
    ],
    deps = [
        # Valdi iOS framework
        "//valdi:valdi_ios",
    ],
    visibility = ["//visibility:public"],
)
```

### Android Module

```python
# In src/android/BUILD.bazel
android_library(
    name = "native_module",
    srcs = [
        "NativeModule.kt",
    ],
    deps = [
        # Valdi Android library
        "//valdi:valdi_android",
    ],
    visibility = ["//visibility:public"],
)
```

## .bazelrc Configuration

Common Bazel configuration options:

```bash
# .bazelrc

# Build settings
build --jobs=auto
build --enable_platform_specific_config

# iOS settings
build:ios --apple_platform_type=ios
build:ios --ios_minimum_os=14.0

# Android settings
build:android --fat_apk_cpu=arm64-v8a,armeabi-v7a
build:android --android_sdk=@androidsdk//:sdk

# macOS settings
build:macos --apple_platform_type=macos
build:macos --macos_minimum_os=11.0

# Debug settings
build:debug --compilation_mode=dbg
build:debug --strip=never

# Release settings
build:release --compilation_mode=opt
build:release --strip=always

# Test settings
test --test_output=errors
test --test_verbose_timeout_warnings
```

## Common Build Commands

```bash
# Build iOS app
bazel build //apps/my_app:my_app --config=ios

# Build Android app
bazel build //apps/my_app:my_app --config=android

# Build for debug
bazel build //apps/my_app:my_app --config=debug

# Build for release
bazel build //apps/my_app:my_app --config=release

# Run tests
bazel test //apps/my_app/...

# Clean build artifacts
bazel clean

# Query dependencies
bazel query 'deps(//apps/my_app:my_app)'
```

## Troubleshooting

### Build Errors

**"Target not found"**
- Check path in deps matches actual BUILD.bazel location
- Verify visibility is set correctly

**"Missing dependency"**
- Add required module to deps array
- Check transitive dependencies

**"TypeScript compilation failed"**
- Verify tsconfig.json is included in srcs
- Check TypeScript syntax errors

### Performance

**Slow builds:**
- Use `--jobs=auto` for parallel builds
- Enable caching with `--disk_cache`
- Use incremental builds (don't clean unnecessarily)

**Out of memory:**
- Limit jobs: `--jobs=4`
- Increase heap: `--host_jvm_args=-Xmx4g`
