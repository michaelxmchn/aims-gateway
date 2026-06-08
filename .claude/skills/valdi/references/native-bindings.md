# Valdi Native Bindings

Guide for integrating native code (C++, Swift, Kotlin) with Valdi TypeScript components.

## Overview

Valdi supports type-safe bindings between TypeScript and native code through:

- **CppModule**: C++ code shared across all platforms
- **NativeModule**: Platform-specific code (iOS/Android)
- **Djinni**: Interface definition language for generating bindings

## C++ Modules (Cross-Platform)

### TypeScript Declaration

```typescript
// src/valdi/my_module/src/CppModule.d.ts
declare module 'CppModule' {
  // Synchronous functions
  export function add(a: number, b: number): number;
  export function multiply(a: number, b: number): number;

  // String operations
  export function formatMessage(template: string, value: number): string;

  // Complex types
  export interface CalculationResult {
    value: number;
    formatted: string;
    timestamp: number;
  }

  export function performCalculation(input: number): CalculationResult;

  // Async operations (returns Promise)
  export function fetchDataAsync(url: string): Promise<string>;
}
```

### C++ Implementation

```cpp
// src/cpp/native_module.hpp
#pragma once

#include <string>
#include <cstdint>

namespace my_module {

struct CalculationResult {
    double value;
    std::string formatted;
    int64_t timestamp;
};

class NativeModuleCpp {
public:
    static double add(double a, double b);
    static double multiply(double a, double b);
    static std::string format_message(const std::string& tmpl, double value);
    static CalculationResult perform_calculation(double input);
};

} // namespace my_module
```

```cpp
// src/cpp/native_module.cpp
#include "native_module.hpp"
#include <ctime>
#include <sstream>
#include <iomanip>

namespace my_module {

double NativeModuleCpp::add(double a, double b) {
    return a + b;
}

double NativeModuleCpp::multiply(double a, double b) {
    return a * b;
}

std::string NativeModuleCpp::format_message(const std::string& tmpl, double value) {
    std::ostringstream oss;
    oss << tmpl << ": " << std::fixed << std::setprecision(2) << value;
    return oss.str();
}

CalculationResult NativeModuleCpp::perform_calculation(double input) {
    double result = input * input;
    return CalculationResult{
        result,
        format_message("Result", result),
        static_cast<int64_t>(std::time(nullptr))
    };
}

} // namespace my_module
```

### Usage in TypeScript

```tsx
import * as CppModule from 'CppModule';

class Calculator extends Component<CalculatorViewModel, ComponentContext> {
  private calculate(): void {
    const sum = CppModule.add(10, 20);
    const product = CppModule.multiply(5, 6);
    const result = CppModule.performCalculation(this.viewModel.input);

    this.viewModel.output = result.formatted;
    this.requestRender();
  }

  onRender() {
    return (
      <view>
        <label>{this.viewModel.output}</label>
        <view onTap={() => this.calculate()}>
          <label>Calculate</label>
        </view>
      </view>
    );
  }
}
```

## Platform-Specific Modules

### TypeScript Declaration

```typescript
// src/valdi/my_module/src/NativeModule.d.ts
declare module 'NativeModule' {
  // Platform info
  export interface PlatformInfo {
    os: 'ios' | 'android' | 'macos';
    version: string;
    deviceModel: string;
  }

  export function getPlatformInfo(): PlatformInfo;

  // Platform-specific UI
  export function showNativeAlert(title: string, message: string): void;
  export function showNativeActionSheet(options: string[]): Promise<number>;

  // Device features
  export function getDeviceId(): string;
  export function hapticFeedback(style: 'light' | 'medium' | 'heavy'): void;

  // Permissions
  export function requestCameraPermission(): Promise<boolean>;
  export function requestLocationPermission(): Promise<boolean>;
}
```

### iOS Implementation (Swift)

```swift
// src/ios/NativeModule.swift
import Foundation
import UIKit

@objc public class NativeModule: NSObject {

    @objc public static func getPlatformInfo() -> [String: Any] {
        return [
            "os": "ios",
            "version": UIDevice.current.systemVersion,
            "deviceModel": UIDevice.current.model
        ]
    }

    @objc public static func showNativeAlert(title: String, message: String) {
        DispatchQueue.main.async {
            let alert = UIAlertController(
                title: title,
                message: message,
                preferredStyle: .alert
            )
            alert.addAction(UIAlertAction(title: "OK", style: .default))

            if let rootVC = UIApplication.shared.keyWindow?.rootViewController {
                rootVC.present(alert, animated: true)
            }
        }
    }

    @objc public static func hapticFeedback(style: String) {
        let generator: UIImpactFeedbackGenerator
        switch style {
        case "light":
            generator = UIImpactFeedbackGenerator(style: .light)
        case "heavy":
            generator = UIImpactFeedbackGenerator(style: .heavy)
        default:
            generator = UIImpactFeedbackGenerator(style: .medium)
        }
        generator.impactOccurred()
    }

    @objc public static func getDeviceId() -> String {
        return UIDevice.current.identifierForVendor?.uuidString ?? ""
    }
}
```

### Android Implementation (Kotlin)

```kotlin
// src/android/NativeModule.kt
package com.example.valdi.modules.my_module

import android.app.AlertDialog
import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.provider.Settings

object NativeModule {

    private var context: Context? = null

    fun initialize(ctx: Context) {
        context = ctx.applicationContext
    }

    fun getPlatformInfo(): Map<String, Any> {
        return mapOf(
            "os" to "android",
            "version" to Build.VERSION.RELEASE,
            "deviceModel" to Build.MODEL
        )
    }

    fun showNativeAlert(title: String, message: String) {
        context?.let { ctx ->
            AlertDialog.Builder(ctx)
                .setTitle(title)
                .setMessage(message)
                .setPositiveButton("OK") { dialog, _ -> dialog.dismiss() }
                .show()
        }
    }

    fun hapticFeedback(style: String) {
        context?.let { ctx ->
            val vibrator = ctx.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                val amplitude = when (style) {
                    "light" -> 50
                    "heavy" -> 255
                    else -> 128
                }
                vibrator?.vibrate(
                    VibrationEffect.createOneShot(10, amplitude)
                )
            } else {
                @Suppress("DEPRECATION")
                vibrator?.vibrate(10)
            }
        }
    }

    fun getDeviceId(): String {
        return context?.let {
            Settings.Secure.getString(it.contentResolver, Settings.Secure.ANDROID_ID)
        } ?: ""
    }
}
```

## Djinni Interface Definitions

Djinni generates cross-platform bindings from interface definitions:

```yaml
# djinni/my_module.djinni

# Simple types
calculation_result = record {
    value: f64;
    formatted: string;
    timestamp: i64;
}

platform_info = record {
    os: string;
    version: string;
    device_model: string;
}

# Interface for C++ implementation
native_calculator = interface +c {
    static add(a: f64, b: f64): f64;
    static multiply(a: f64, b: f64): f64;
    static perform_calculation(input: f64): calculation_result;
}

# Interface for platform-specific implementation
platform_module = interface +o +j {
    # +o = Objective-C, +j = Java
    static get_platform_info(): platform_info;
    static show_native_alert(title: string, message: string);
    static haptic_feedback(style: string);
    static get_device_id(): string;
}
```

Generate bindings:

```bash
djinni \
    --idl djinni/my_module.djinni \
    --cpp-out src/cpp/generated \
    --objc-out src/ios/generated \
    --java-out src/android/generated \
    --ts-out src/valdi/my_module/src/generated
```

## Best Practices

### 1. Keep Native Code Minimal

Only use native bindings when necessary:
- Platform APIs not available in TypeScript
- Performance-critical computations
- Hardware access (camera, sensors)

### 2. Type Safety

Always provide complete TypeScript declarations:

```typescript
// GOOD - Complete types
declare module 'CppModule' {
  export interface UserData {
    id: string;
    name: string;
    email: string;
  }
  export function fetchUser(id: string): Promise<UserData>;
}

// BAD - Loose types
declare module 'CppModule' {
  export function fetchUser(id: string): Promise<any>;
}
```

### 3. Error Handling

Handle errors gracefully across the boundary:

```typescript
// TypeScript
try {
  const result = await NativeModule.requestCameraPermission();
  if (!result) {
    // Permission denied
  }
} catch (error) {
  // Native error occurred
  console.error('Camera permission error:', error);
}
```

```swift
// Swift - Return error information
@objc public static func requestCameraPermission(
    completion: @escaping (Bool, String?) -> Void
) {
    AVCaptureDevice.requestAccess(for: .video) { granted in
        if granted {
            completion(true, nil)
        } else {
            completion(false, "Camera access denied by user")
        }
    }
}
```

### 4. Thread Safety

Native code may run on different threads:

```swift
// Swift - Ensure main thread for UI operations
@objc public static func showAlert(message: String) {
    DispatchQueue.main.async {
        // UI code here
    }
}
```

```kotlin
// Kotlin - Use coroutines for async
suspend fun fetchDataAsync(): String = withContext(Dispatchers.IO) {
    // Network/IO operation
}
```

### 5. Memory Management

Be careful with object lifecycles:

```cpp
// C++ - Use smart pointers
std::shared_ptr<DataObject> createData() {
    return std::make_shared<DataObject>();
}

// Avoid raw pointers that could leak
DataObject* createData() {  // BAD
    return new DataObject();
}
```

## Common Patterns

### Async Native Calls

```typescript
// TypeScript declaration
declare module 'NativeModule' {
  export function fetchDataAsync(url: string): Promise<string>;
}

// Usage
async function loadData() {
  try {
    const data = await NativeModule.fetchDataAsync('/api/data');
    return JSON.parse(data);
  } catch (error) {
    console.error('Failed to fetch:', error);
    return null;
  }
}
```

### Callbacks

```typescript
// TypeScript declaration
declare module 'NativeModule' {
  export type ProgressCallback = (progress: number) => void;
  export function downloadFile(
    url: string,
    onProgress: ProgressCallback
  ): Promise<string>;
}

// Usage
await NativeModule.downloadFile(url, (progress) => {
  this.viewModel.downloadProgress = progress;
  this.requestRender();
});
```

### Event Streams

```typescript
// TypeScript declaration
declare module 'NativeModule' {
  export interface LocationUpdate {
    latitude: number;
    longitude: number;
    accuracy: number;
  }

  export function startLocationUpdates(
    callback: (location: LocationUpdate) => void
  ): void;

  export function stopLocationUpdates(): void;
}
```

## Debugging Native Code

### iOS (Xcode)
1. Open generated Xcode project
2. Set breakpoints in Swift/Objective-C code
3. Use LLDB for debugging

### Android (Android Studio)
1. Open generated Android project
2. Set breakpoints in Kotlin/Java code
3. Use logcat for logging

### C++ (Various)
- Use `std::cout` or logging frameworks
- Attach debugger to running process
- Use sanitizers (AddressSanitizer, etc.)
