# Platform-Specific Code in Solito

This guide covers platform detection, conditional rendering, platform-specific file extensions, and best practices for handling web vs native differences.

## Core Principle: Share First, Specialize Only When Needed

**80% of your code should work on both platforms.** Only create platform-specific code when absolutely necessary.

```
✅ GOOD: Shared by default
packages/app/features/profile/screen.tsx  (works on both)

❌ BAD: Duplicated unnecessarily
packages/app/features/profile/screen.web.tsx
packages/app/features/profile/screen.native.tsx
```

## Platform Detection

### Using Platform.OS

React Native's `Platform` module works on both web and native.

```tsx
import { Platform } from 'react-native'

export function PlatformInfo() {
  return (
    <View>
      <Text>Platform: {Platform.OS}</Text>
      {/* Platform.OS values: 'ios', 'android', 'web' */}
    </View>
  )
}
```

**Conditional rendering:**
```tsx
import { Platform, View, Text } from 'react-native'

export function VideoPlayer({ url }) {
  if (Platform.OS === 'web') {
    return (
      <video src={url} controls style={{ width: '100%' }} />
    )
  }

  // Native platforms
  return <Video source={{ uri: url }} style={{ width: '100%' }} />
}
```

**Platform-specific styles:**
```tsx
const styles = {
  container: {
    padding: Platform.select({
      ios: 16,
      android: 12,
      web: 20,
    }),
    ...Platform.select({
      ios: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.1,
      },
      web: {
        boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
      },
    }),
  },
}
```

### Platform.select()

```tsx
import { Platform } from 'react-native'

const fontSize = Platform.select({
  ios: 16,
  android: 14,
  web: 18,
  default: 16, // fallback
})

const Component = Platform.select({
  web: () => WebComponent,
  native: () => NativeComponent,
})()
```

## Platform-Specific File Extensions

Metro bundler and Next.js automatically resolve platform-specific files.

### File Resolution Order

**Given this structure:**
```
components/
  button.tsx
  button.web.tsx
  button.native.tsx
  button.ios.tsx
  button.android.tsx
```

**Resolution priority:**

**On Web (Next.js):**
1. `button.web.tsx` ✅
2. `button.tsx`

**On iOS:**
1. `button.ios.tsx` ✅
2. `button.native.tsx`
3. `button.tsx`

**On Android:**
1. `button.android.tsx` ✅
2. `button.native.tsx`
3. `button.tsx`

### Example: Platform-Specific Components

**Base component (shared):**
```tsx
// components/button.tsx
import { Text, Pressable } from 'react-native'

export function Button({ onPress, children }) {
  return (
    <Pressable onPress={onPress}>
      <Text>{children}</Text>
    </Pressable>
  )
}
```

**Web-specific override:**
```tsx
// components/button.web.tsx
export function Button({ onPress, children }) {
  return (
    <button onClick={onPress} className="btn">
      {children}
    </button>
  )
}
```

**Usage:**
```tsx
import { Button } from 'app/components/button'

// Automatically uses:
// - button.web.tsx on web
// - button.tsx on native
export function Screen() {
  return <Button onPress={handleClick}>Click me</Button>
}
```

## Common Platform-Specific Scenarios

### Video Players

```tsx
// components/video-player.tsx
export interface VideoPlayerProps {
  url: string
  autoplay?: boolean
}
```

```tsx
// components/video-player.web.tsx
import type { VideoPlayerProps } from './video-player'

export function VideoPlayer({ url, autoplay }: VideoPlayerProps) {
  return (
    <video
      src={url}
      controls
      autoPlay={autoplay}
      style={{ width: '100%' }}
    />
  )
}
```

```tsx
// components/video-player.native.tsx
import { Video } from 'expo-av'
import type { VideoPlayerProps } from './video-player'

export function VideoPlayer({ url, autoplay }: VideoPlayerProps) {
  return (
    <Video
      source={{ uri: url }}
      useNativeControls
      shouldPlay={autoplay}
      style={{ width: '100%', height: 300 }}
    />
  )
}
```

### Maps

```tsx
// components/map.web.tsx
export function Map({ latitude, longitude }) {
  return (
    <iframe
      src={`https://maps.google.com/maps?q=${latitude},${longitude}&output=embed`}
      style={{ width: '100%', height: 400, border: 0 }}
    />
  )
}
```

```tsx
// components/map.native.tsx
import MapView, { Marker } from 'react-native-maps'

export function Map({ latitude, longitude }) {
  return (
    <MapView
      style={{ width: '100%', height: 400 }}
      initialRegion={{
        latitude,
        longitude,
        latitudeDelta: 0.01,
        longitudeDelta: 0.01,
      }}
    >
      <Marker coordinate={{ latitude, longitude }} />
    </MapView>
  )
}
```

### Image Optimization

```tsx
// components/optimized-image.web.tsx
import Image from 'next/image'

export function OptimizedImage({ src, width, height, alt }) {
  return (
    <Image
      src={src}
      width={width}
      height={height}
      alt={alt}
      priority
    />
  )
}
```

```tsx
// components/optimized-image.native.tsx
import { Image } from 'expo-image'

export function OptimizedImage({ src, width, height, alt }) {
  return (
    <Image
      source={{ uri: src }}
      style={{ width, height }}
      contentFit="cover"
      placeholder={blurhash}
    />
  )
}
```

### File Uploads

```tsx
// components/file-upload.web.tsx
export function FileUpload({ onFileSelect }) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) onFileSelect(file)
  }

  return <input type="file" onChange={handleChange} />
}
```

```tsx
// components/file-upload.native.tsx
import * as DocumentPicker from 'expo-document-picker'

export function FileUpload({ onFileSelect }) {
  const handlePress = async () => {
    const result = await DocumentPicker.getDocumentAsync()
    if (result.type === 'success') {
      onFileSelect(result)
    }
  }

  return (
    <Pressable onPress={handlePress}>
      <Text>Select File</Text>
    </Pressable>
  )
}
```

## Conditional Logic Patterns

### Feature Detection

```tsx
import { Platform } from 'react-native'

const hasCamera = Platform.select({
  web: 'mediaDevices' in navigator,
  native: true,
})

export function CameraButton() {
  if (!hasCamera) {
    return <Text>Camera not available</Text>
  }

  return <Button onPress={openCamera}>Open Camera</Button>
}
```

### Environment-Based

```tsx
const API_URL = Platform.select({
  web: process.env.NEXT_PUBLIC_API_URL,
  native: process.env.EXPO_PUBLIC_API_URL,
})
```

### Capability-Based

```tsx
import { Platform, Dimensions } from 'react-native'

const isLargeScreen = Dimensions.get('window').width > 768

export function Layout({ children }) {
  const showSidebar = Platform.OS === 'web' && isLargeScreen

  return (
    <View>
      {showSidebar && <Sidebar />}
      <Main>{children}</Main>
    </View>
  )
}
```

## Platform-Specific Hooks

### useWindowDimensions

```tsx
import { useWindowDimensions } from 'react-native'

export function ResponsiveLayout() {
  const { width } = useWindowDimensions()
  const isMobile = width < 768

  return (
    <View style={{ flexDirection: isMobile ? 'column' : 'row' }}>
      <Sidebar />
      <Content />
    </View>
  )
}
```

### Custom Platform Hooks

```tsx
// hooks/use-platform-behavior.ts
import { Platform } from 'react-native'
import { useState, useEffect } from 'react'

export function usePlatformBehavior() {
  const [isHovering, setIsHovering] = useState(false)

  if (Platform.OS === 'web') {
    return {
      onMouseEnter: () => setIsHovering(true),
      onMouseLeave: () => setIsHovering(false),
      isHovering,
    }
  }

  // Native: use press states
  return {
    onPressIn: () => setIsHovering(true),
    onPressOut: () => setIsHovering(false),
    isHovering,
  }
}
```

## Styling Differences

### NativeWind Platform Modifiers

```tsx
// Tailwind classes with platform modifiers
<View className="p-4 web:p-6 native:p-2">
  <Text className="text-base web:text-lg native:text-sm">
    Platform-specific sizing
  </Text>
</View>
```

### Platform-Specific StyleSheet

```tsx
import { StyleSheet, Platform } from 'react-native'

const styles = StyleSheet.create({
  container: {
    padding: 16,
    ...Platform.select({
      web: {
        maxWidth: 1200,
        margin: '0 auto',
      },
      native: {
        flex: 1,
      },
    }),
  },
})
```

### Responsive Design

```tsx
import { useWindowDimensions } from 'react-native'

export function ResponsiveText() {
  const { width } = useWindowDimensions()

  const fontSize = width > 768 ? 24 : 16
  const padding = width > 768 ? 32 : 16

  return (
    <Text style={{ fontSize, padding }}>
      Responsive text
    </Text>
  )
}
```

## API Differences

### Navigation

```tsx
import { useRouter } from 'solito/router'
import { Platform } from 'react-native'

export function useBackButton() {
  const router = useRouter()

  const goBack = () => {
    if (Platform.OS === 'web' && window.history.length <= 1) {
      router.push('/')
    } else {
      router.back()
    }
  }

  return { goBack }
}
```

### Storage

```tsx
// lib/storage.web.ts
export const storage = {
  async setItem(key: string, value: string) {
    localStorage.setItem(key, value)
  },
  async getItem(key: string) {
    return localStorage.getItem(key)
  },
}
```

```tsx
// lib/storage.native.ts
import AsyncStorage from '@react-native-async-storage/async-storage'

export const storage = {
  setItem: AsyncStorage.setItem,
  getItem: AsyncStorage.getItem,
}
```

### Notifications

```tsx
// lib/notifications.web.ts
export async function requestPermission() {
  return Notification.requestPermission()
}

export function sendNotification(title: string, body: string) {
  new Notification(title, { body })
}
```

```tsx
// lib/notifications.native.ts
import * as Notifications from 'expo-notifications'

export async function requestPermission() {
  const { status } = await Notifications.requestPermissionsAsync()
  return status === 'granted'
}

export async function sendNotification(title: string, body: string) {
  await Notifications.scheduleNotificationAsync({
    content: { title, body },
    trigger: null,
  })
}
```

## Testing Platform-Specific Code

### Jest Platform Mocking

```tsx
// __tests__/video-player.test.tsx
import { Platform } from 'react-native'

jest.mock('react-native/Libraries/Utilities/Platform', () => ({
  OS: 'web',
  select: jest.fn((obj) => obj.web),
}))

test('renders web video player', () => {
  const { getByTestId } = render(<VideoPlayer url="test.mp4" />)
  expect(getByTestId('web-video')).toBeTruthy()
})
```

### Testing Both Platforms

```tsx
describe.each(['web', 'ios', 'android'])('Button on %s', (platform) => {
  beforeEach(() => {
    Platform.OS = platform
  })

  it('renders correctly', () => {
    const { getByText } = render(<Button>Click me</Button>)
    expect(getByText('Click me')).toBeTruthy()
  })
})
```

## Best Practices

1. **Default to shared code** - Only use platform-specific when necessary
2. **Use file extensions** - Cleaner than Platform.select() for components
3. **Share interfaces** - Define types in base file, implement in platform files
4. **Abstract platform APIs** - Create unified wrappers (storage, notifications)
5. **Test both platforms** - Don't assume code works everywhere
6. **Document differences** - Comment why platform-specific code is needed
7. **Use TypeScript** - Catch platform-specific API mismatches
8. **Prefer NativeWind modifiers** - `web:` and `native:` for simple style differences
9. **Avoid deep conditionals** - Extract to separate files if logic is complex
10. **Monitor bundle size** - Platform-specific code can bloat bundles

## Anti-Patterns

### ❌ Duplicating Entire Screens

```tsx
// DON'T: Separate screens for minor differences
packages/app/features/profile/screen.web.tsx    // 95% identical
packages/app/features/profile/screen.native.tsx // 95% identical
```

**✅ DO: Extract platform-specific components**
```tsx
packages/app/features/profile/
  screen.tsx              // Shared screen logic
  components/
    avatar.web.tsx        // Only avatar differs
    avatar.native.tsx
```

### ❌ Inline Platform Checks Everywhere

```tsx
// DON'T: Scattered platform checks
<View>
  {Platform.OS === 'web' && <WebHeader />}
  {Platform.OS !== 'web' && <NativeHeader />}
  {/* ... more checks ... */}
</View>
```

**✅ DO: Use file extensions**
```tsx
// header.web.tsx and header.native.tsx
import { Header } from './header'

<View>
  <Header />
</View>
```

### ❌ Platform-Specific Business Logic

```tsx
// DON'T: Different business logic per platform
if (Platform.OS === 'web') {
  // Web-specific calculation
  price = basePrice * 1.1
} else {
  // Native-specific calculation
  price = basePrice * 1.2
}
```

**✅ DO: Keep business logic platform-agnostic**
```tsx
// Same logic everywhere
const calculatePrice = (basePrice: number) => {
  return basePrice * TAX_RATE
}
```

---

**Remember:** Platform-specific code should be the exception, not the rule. When you do need it, use file extensions and abstractions to keep code clean and maintainable.
