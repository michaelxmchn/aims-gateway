# Common Pitfalls in Solito Development

This guide documents frequent mistakes when building Solito applications and how to avoid or fix them.

## Navigation Issues

### Pitfall 1: Using Platform-Specific Navigation Libraries

❌ **WRONG:**
```tsx
// DON'T: Using Next.js Link directly
import Link from 'next/link'

<Link href="/profile">Profile</Link>
```

```tsx
// DON'T: Using React Navigation Link directly
import { Link } from '@react-navigation/native'

<Link to={{ screen: 'Profile' }}>Profile</Link>
```

✅ **CORRECT:**
```tsx
// DO: Use Solito's unified Link
import { Link } from 'solito/link'

<Link href="/profile">
  <Text>Profile</Text>
</Link>
```

**Why:** Solito's Link works on both platforms. Platform-specific links break cross-platform compatibility.

---

### Pitfall 2: Hardcoding Absolute URLs

❌ **WRONG:**
```tsx
<Link href="https://myapp.com/profile">
  <Text>Profile</Text>
</Link>
```

✅ **CORRECT:**
```tsx
<Link href="/profile">
  <Text>Profile</Text>
</Link>
```

**Why:** Absolute URLs work on web but break native navigation. Use relative paths.

---

### Pitfall 3: Incorrect Param Access

❌ **WRONG:**
```tsx
// Next.js pattern - doesn't work with Solito
export default function Page({ params }: { params: { id: string } }) {
  return <Text>{params.id}</Text>
}
```

✅ **CORRECT:**
```tsx
import { useParams } from 'solito/router'

export function UserScreen() {
  const { id } = useParams<{ id: string }>()
  return <Text>{id}</Text>
}
```

**Why:** Solito uses hooks for params, not component props. Works on both platforms.

---

### Pitfall 4: Missing Navigation Provider

❌ **WRONG:**
```tsx
// apps/expo/app/_layout.tsx
export default function RootLayout() {
  return <Stack />  // Missing Solito provider
}
```

✅ **CORRECT:**
```tsx
import { Provider } from 'app/provider'

export default function RootLayout() {
  return (
    <Provider>
      <Stack />
    </Provider>
  )
}
```

**Why:** Solito needs a navigation provider to sync state across platforms.

---

### Pitfall 5: Navigation State Persistence

❌ **WRONG:**
```tsx
// State lost on web refresh
router.push({
  pathname: '/checkout',
  state: { cart: items },  // Lost on refresh
})
```

✅ **CORRECT:**
```tsx
// Use query params
router.push({
  pathname: '/checkout',
  query: { items: JSON.stringify(items) },
})

// Or better: use global state
const cart = useCartStore((state) => state.items)
```

**Why:** Navigation state doesn't persist on web. Use query params or global state.

## Import Issues

### Pitfall 6: Importing from Wrong Packages

❌ **WRONG:**
```tsx
// In packages/app
import Image from 'next/image'  // Next.js only
import { useNavigation } from '@react-navigation/native'  // RN only
```

✅ **CORRECT:**
```tsx
// Use cross-platform alternatives
import { Image } from 'react-native'
import { useRouter } from 'solito/router'

// Or create platform-specific files
import { OptimizedImage } from 'app/components/optimized-image'
```

**Why:** Platform-specific imports break on the other platform. Use shared APIs.

---

### Pitfall 7: Direct Next.js or React Native Imports

❌ **WRONG:**
```tsx
// In packages/app
import { useRouter } from 'next/router'
import { ScrollView } from 'react-native-gesture-handler'
```

✅ **CORRECT:**
```tsx
import { useRouter } from 'solito/router'
import { ScrollView } from 'react-native'
```

**Why:** Keep packages/app platform-agnostic. Platform-specific code belongs in apps/.

---

### Pitfall 8: Missing React Native Web Setup

❌ **WRONG:**
```tsx
// apps/next without react-native-web
import { View } from 'react-native'  // Breaks on web
```

✅ **CORRECT:**
```json
// apps/next/package.json
{
  "dependencies": {
    "react-native-web": "^0.19.0"
  }
}
```

```js
// next.config.js
const { withExpo } = require('@expo/next-adapter')

module.exports = withExpo({
  transpilePackages: [
    'react-native',
    'react-native-web',
    'solito',
    'app',
  ],
})
```

**Why:** React Native components need react-native-web to work on Next.js.

## Styling Issues

### Pitfall 9: Using Web-Only CSS

❌ **WRONG:**
```tsx
<View style={{ display: 'grid' }}>  // grid not supported in RN
  <div className="col-span-2" />    // div doesn't exist in RN
</View>
```

✅ **CORRECT:**
```tsx
// Use flexbox (supported everywhere)
<View style={{ flexDirection: 'row', gap: 16 }}>
  <View style={{ flex: 2 }} />
</View>

// Or use NativeWind
<View className="flex flex-row gap-4">
  <View className="flex-2" />
</View>
```

**Why:** React Native has limited CSS support. Stick to flexbox and supported properties.

---

### Pitfall 10: Forgetting NativeWind Babel Plugin

❌ **WRONG:**
```tsx
// Tailwind classes don't work on native
<View className="bg-blue-500 p-4">
  <Text className="text-white">Hello</Text>
</View>
```

✅ **CORRECT:**
```js
// apps/expo/babel.config.js
module.exports = function (api) {
  api.cache(true)
  return {
    presets: ['babel-preset-expo'],
    plugins: ['nativewind/babel'],  // Required
  }
}
```

```js
// tailwind.config.js
module.exports = {
  content: ['./app/**/*.{js,jsx,ts,tsx}', '../../packages/app/**/*.{js,jsx,ts,tsx}'],
  presets: [require('nativewind/preset')],
}
```

**Why:** NativeWind requires Babel plugin to transform Tailwind classes for React Native.

---

### Pitfall 11: Platform-Specific Style Properties

❌ **WRONG:**
```tsx
<View style={{
  boxShadow: '0 2px 4px rgba(0,0,0,0.1)',  // Web only
  shadowColor: '#000',                       // Native only
}}>
```

✅ **CORRECT:**
```tsx
import { Platform } from 'react-native'

<View style={{
  ...Platform.select({
    web: {
      boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
    },
    native: {
      shadowColor: '#000',
      shadowOffset: { width: 0, height: 2 },
      shadowOpacity: 0.1,
      shadowRadius: 4,
    },
  }),
}}>
```

**Why:** Shadow syntax differs between web and native. Use Platform.select().

## Monorepo Configuration

### Pitfall 12: Incorrect Workspace References

❌ **WRONG:**
```json
// apps/next/package.json
{
  "dependencies": {
    "app": "1.0.0"  // Wrong: treats as npm package
  }
}
```

✅ **CORRECT:**
```json
{
  "dependencies": {
    "app": "workspace:*"  // Correct: references local workspace
  }
}
```

**Why:** Workspace protocol ensures monorepo packages are linked correctly.

---

### Pitfall 13: Version Mismatches

❌ **WRONG:**
```json
// packages/app/package.json
{ "dependencies": { "react": "18.2.0" } }

// apps/next/package.json
{ "dependencies": { "react": "18.3.0" } }  // Different version
```

✅ **CORRECT:**
```json
// Root package.json
{
  "pnpm": {
    "overrides": {
      "react": "18.2.0",
      "react-native": "0.73.0"
    }
  }
}
```

**Why:** React version mismatches cause runtime errors. Sync versions across packages.

---

### Pitfall 14: Metro Bundler Not Watching Workspace

❌ **WRONG:**
```js
// apps/expo/metro.config.js
const config = getDefaultConfig(__dirname)
// Doesn't watch packages/app
```

✅ **CORRECT:**
```js
const { getDefaultConfig } = require('expo/metro-config')
const path = require('path')

const projectRoot = __dirname
const workspaceRoot = path.resolve(projectRoot, '../..')

const config = getDefaultConfig(projectRoot)

config.watchFolders = [workspaceRoot]
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
]

module.exports = config
```

**Why:** Metro needs to watch the entire monorepo to detect changes in packages/app.

## TypeScript Issues

### Pitfall 15: Missing Path Mappings

❌ **WRONG:**
```tsx
// TypeScript can't resolve 'app/*'
import { Button } from 'app/components/button'  // Error
```

✅ **CORRECT:**
```json
// apps/next/tsconfig.json
{
  "compilerOptions": {
    "baseUrl": ".",
    "paths": {
      "app/*": ["../../packages/app/*"]
    }
  }
}
```

**Why:** TypeScript needs path mappings to resolve workspace imports.

---

### Pitfall 16: Type Errors from Platform-Specific Files

❌ **WRONG:**
```tsx
// button.web.tsx
export function Button({ onClick }: { onClick: () => void }) { }

// button.native.tsx
export function Button({ onPress }: { onPress: () => void }) { }

// Usage causes type errors
import { Button } from './button'
<Button onClick={handler} />  // Error: onClick doesn't exist on native
```

✅ **CORRECT:**
```tsx
// button.tsx (shared interface)
export interface ButtonProps {
  onPress: () => void
  children: React.ReactNode
}

// button.web.tsx
export function Button({ onPress, children }: ButtonProps) {
  return <button onClick={onPress}>{children}</button>
}

// button.native.tsx
import { Pressable, Text } from 'react-native'

export function Button({ onPress, children }: ButtonProps) {
  return <Pressable onPress={onPress}><Text>{children}</Text></Pressable>
}
```

**Why:** Shared interface ensures consistent API across platforms.

## Performance Issues

### Pitfall 17: Large Bundle on Web

❌ **WRONG:**
```tsx
// Imports entire library on web
import { Camera } from 'react-native-camera'  // 500KB+

export function ProfileScreen() {
  return <View>...</View>  // Doesn't even use Camera
}
```

✅ **CORRECT:**
```tsx
// Dynamic import for heavy features
const Camera = dynamic(() => import('react-native-camera'), {
  ssr: false,
})

export function CameraScreen() {
  return <Camera />
}
```

**Why:** Native-only packages bloat web bundles. Use dynamic imports.

---

### Pitfall 18: Not Using Platform-Specific Optimizations

❌ **WRONG:**
```tsx
// Same image component everywhere
<Image source={{ uri: url }} style={{ width: 300, height: 200 }} />
```

✅ **CORRECT:**
```tsx
// optimized-image.web.tsx
import NextImage from 'next/image'
export function OptimizedImage({ src, width, height, alt }) {
  return <NextImage src={src} width={width} height={height} alt={alt} />
}

// optimized-image.native.tsx
import { Image } from 'expo-image'
export function OptimizedImage({ src, width, height }) {
  return <Image source={{ uri: src }} style={{ width, height }} />
}
```

**Why:** Platform-specific optimizations improve performance significantly.

## Environment Variables

### Pitfall 19: Incorrect Env Var Prefixes

❌ **WRONG:**
```tsx
// Won't work on Expo
const apiUrl = process.env.NEXT_PUBLIC_API_URL

// Won't work on Next.js
const apiUrl = process.env.EXPO_PUBLIC_API_URL
```

✅ **CORRECT:**
```tsx
import { Platform } from 'react-native'

const apiUrl = Platform.select({
  web: process.env.NEXT_PUBLIC_API_URL,
  native: process.env.EXPO_PUBLIC_API_URL,
})
```

**Why:** Next.js uses NEXT_PUBLIC_, Expo uses EXPO_PUBLIC_. Handle both.

---

### Pitfall 20: Not Restarting After Env Changes

❌ **WRONG:**
```bash
# Change .env file
# Hot reload doesn't pick up changes
```

✅ **CORRECT:**
```bash
# Change .env file
# Restart dev servers
pnpm dev  # Restart both Next.js and Expo
```

**Why:** Environment variables are bundled at build time. Restart required.

## Testing Issues

### Pitfall 21: Not Testing Both Platforms

❌ **WRONG:**
```bash
# Only test on web
pnpm test  # Jest runs web tests only
```

✅ **CORRECT:**
```json
// package.json
{
  "scripts": {
    "test": "jest",
    "test:web": "jest --selectProjects web",
    "test:native": "jest --selectProjects native"
  }
}
```

```js
// jest.config.js
module.exports = {
  projects: [
    { displayName: 'web', testEnvironment: 'jsdom', testMatch: ['**/*.web.test.tsx'] },
    { displayName: 'native', preset: 'jest-expo', testMatch: ['**/*.native.test.tsx'] },
  ],
}
```

**Why:** Code can work on one platform but break on another. Test both.

## Authentication Issues

### Pitfall 22: Platform-Specific Auth Flow

❌ **WRONG:**
```tsx
// Different auth logic per platform
if (Platform.OS === 'web') {
  await signInWithPopup()
} else {
  await signInWithRedirect()
}
```

✅ **CORRECT:**
```tsx
// Use cross-platform auth provider (Clerk, Supabase)
import { useAuth } from '@clerk/clerk-expo'

const { signIn } = useAuth()
await signIn.create({ identifier: email, password })
```

**Why:** Cross-platform auth providers handle platform differences internally.

---

### Pitfall 23: Token Storage Differences

❌ **WRONG:**
```tsx
// localStorage doesn't exist on native
localStorage.setItem('token', token)
```

✅ **CORRECT:**
```tsx
// storage.ts (platform-agnostic interface)
import { Platform } from 'react-native'

const storage = Platform.select({
  web: {
    setItem: (key, value) => localStorage.setItem(key, value),
    getItem: (key) => localStorage.getItem(key),
  },
  native: {
    setItem: (key, value) => AsyncStorage.setItem(key, value),
    getItem: (key) => AsyncStorage.getItem(key),
  },
})

export { storage }
```

**Why:** Storage APIs differ. Create unified interface.

## Best Practices to Avoid Pitfalls

1. **Always use Solito navigation** - Never import from next/router or @react-navigation
2. **Test on both platforms regularly** - Don't wait until the end
3. **Use TypeScript strictly** - Catch platform mismatches early
4. **Keep packages/app platform-agnostic** - Platform code goes in apps/
5. **Sync dependency versions** - Especially react and react-native
6. **Configure Metro and Next.js correctly** - Follow monorepo best practices
7. **Use NativeWind for styling** - Consistent API across platforms
8. **Create platform-specific files** - Better than scattered Platform.select()
9. **Read Solito docs** - Stay updated on best practices
10. **Check bundle sizes** - Optimize for both web and native

---

**Remember:** Most pitfalls come from mixing platform-specific code or not configuring the monorepo correctly. When in doubt, check the official Solito starter template for reference.
