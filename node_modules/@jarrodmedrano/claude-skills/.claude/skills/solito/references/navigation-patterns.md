# Navigation Patterns in Solito

This guide covers navigation patterns, routing, links, parameters, and navigation hooks in Solito applications.

## Core Navigation Components

### Link Component

The `Link` component from `solito/link` works across both web and native platforms.

**Basic usage:**
```tsx
import { Link } from 'solito/link'
import { View, Text } from 'react-native'

export function HomeScreen() {
  return (
    <View>
      <Link href="/profile">
        <Text>Go to Profile</Text>
      </Link>
    </View>
  )
}
```

**With custom styling:**
```tsx
<Link href="/settings">
  <View className="bg-blue-500 p-4 rounded-lg">
    <Text className="text-white font-bold">Settings</Text>
  </View>
</Link>
```

**External links:**
```tsx
<Link href="https://solito.dev" target="_blank">
  <Text>Visit Solito Docs</Text>
</Link>
```

### Router Hook

The `useRouter` hook provides programmatic navigation.

```tsx
import { useRouter } from 'solito/router'

export function LoginScreen() {
  const router = useRouter()

  const handleLogin = async () => {
    await loginUser()
    router.push('/dashboard')
  }

  return (
    <Button onPress={handleLogin}>
      Login
    </Button>
  )
}
```

**Router methods:**
```tsx
const router = useRouter()

// Navigate forward
router.push('/profile')

// Navigate with replace (no back button)
router.replace('/dashboard')

// Navigate back
router.back()
```

## Route Parameters

### Static Routes

Routes without parameters:

```
/                  -> Home
/profile           -> Profile
/settings          -> Settings
/about             -> About
```

### Dynamic Routes

**Single parameter:**

```tsx
// Route: /user/[id]
// apps/next/app/user/[id]/page.tsx
// apps/expo/app/user/[id].tsx

import { UserDetailScreen } from 'app/features/user/detail-screen'

export default UserDetailScreen
```

**Screen implementation:**
```tsx
// packages/app/features/user/detail-screen.tsx
import { useParams } from 'solito/router'

export function UserDetailScreen() {
  const { id } = useParams<{ id: string }>()

  return (
    <View>
      <Text>User ID: {id}</Text>
    </View>
  )
}
```

**Linking to dynamic routes:**
```tsx
<Link href={`/user/${userId}`}>
  <Text>View User</Text>
</Link>

// Or with object syntax
<Link
  href={{
    pathname: '/user/[id]',
    params: { id: userId },
  }}
>
  <Text>View User</Text>
</Link>
```

### Multiple Parameters

```tsx
// Route: /post/[category]/[slug]
// apps/next/app/post/[category]/[slug]/page.tsx
// apps/expo/app/post/[category]/[slug].tsx

export function PostDetailScreen() {
  const { category, slug } = useParams<{
    category: string
    slug: string
  }>()

  return (
    <View>
      <Text>Category: {category}</Text>
      <Text>Slug: {slug}</Text>
    </View>
  )
}
```

**Linking:**
```tsx
<Link href={`/post/${category}/${slug}`}>
  <Text>Read Post</Text>
</Link>
```

### Catch-All Routes

```tsx
// Route: /docs/[...slug]
// Matches: /docs/a, /docs/a/b, /docs/a/b/c

export function DocsScreen() {
  const { slug } = useParams<{ slug: string[] }>()

  // slug is an array: ['getting-started', 'installation']
  const path = slug?.join('/') ?? ''

  return <Text>Docs Path: {path}</Text>
}
```

## Query Parameters

**Passing query params:**
```tsx
<Link
  href={{
    pathname: '/search',
    query: { q: 'react', sort: 'newest' },
  }}
>
  <Text>Search React</Text>
</Link>
```

**Reading query params:**
```tsx
import { useSearchParams } from 'solito/router'

export function SearchScreen() {
  const searchParams = useSearchParams()
  const query = searchParams.get('q')
  const sort = searchParams.get('sort')

  return (
    <View>
      <Text>Query: {query}</Text>
      <Text>Sort: {sort}</Text>
    </View>
  )
}
```

**Programmatic navigation with query params:**
```tsx
const router = useRouter()

router.push({
  pathname: '/search',
  query: { q: searchTerm, filter: 'all' },
})
```

## Navigation State

### Passing State Between Screens

**Not recommended** - Use query params or global state instead:
```tsx
// ❌ BAD: State doesn't persist on web refresh
router.push({
  pathname: '/checkout',
  state: { cart: items }, // Lost on refresh
})
```

**✅ GOOD: Use query params for simple data:**
```tsx
router.push({
  pathname: '/checkout',
  query: { items: JSON.stringify(items) },
})
```

**✅ BETTER: Use global state (Zustand, Jotai, etc.):**
```tsx
// In checkout screen
const cart = useCartStore((state) => state.items)
```

## Navigation Guards & Protected Routes

**Redirect unauthenticated users:**

```tsx
// packages/app/features/dashboard/screen.tsx
import { useAuth } from 'app/lib/auth'
import { useRouter } from 'solito/router'
import { useEffect } from 'react'

export function DashboardScreen() {
  const { user, loading } = useAuth()
  const router = useRouter()

  useEffect(() => {
    if (!loading && !user) {
      router.replace('/login')
    }
  }, [user, loading, router])

  if (loading) return <LoadingSpinner />
  if (!user) return null

  return <DashboardContent />
}
```

**Higher-order component approach:**
```tsx
// packages/app/lib/with-auth.tsx
export function withAuth<P extends object>(
  Component: React.ComponentType<P>
) {
  return function AuthenticatedComponent(props: P) {
    const { user, loading } = useAuth()
    const router = useRouter()

    useEffect(() => {
      if (!loading && !user) {
        router.replace('/login')
      }
    }, [user, loading, router])

    if (loading) return <LoadingSpinner />
    if (!user) return null

    return <Component {...props} />
  }
}

// Usage
export const DashboardScreen = withAuth(DashboardContent)
```

## Nested Navigation

### Tab Navigation (Native)

```tsx
// apps/expo/app/(tabs)/_layout.tsx
import { Tabs } from 'expo-router'

export default function TabLayout() {
  return (
    <Tabs>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          tabBarIcon: ({ color }) => <HomeIcon color={color} />,
        }}
      />
      <Tabs.Screen
        name="profile"
        options={{
          title: 'Profile',
          tabBarIcon: ({ color }) => <ProfileIcon color={color} />,
        }}
      />
    </Tabs>
  )
}
```

### Stack Navigation (Native)

```tsx
// apps/expo/app/_layout.tsx
import { Stack } from 'expo-router'

export default function RootLayout() {
  return (
    <Stack>
      <Stack.Screen
        name="index"
        options={{ title: 'Home' }}
      />
      <Stack.Screen
        name="profile"
        options={{ title: 'Profile' }}
      />
      <Stack.Screen
        name="settings"
        options={{
          title: 'Settings',
          presentation: 'modal', // Modal presentation
        }}
      />
    </Stack>
  )
}
```

## Navigation Events

### Listen to Navigation Changes

```tsx
import { useEffect } from 'react'
import { useRouter } from 'solito/router'

export function AnalyticsProvider({ children }) {
  const router = useRouter()

  useEffect(() => {
    // Track page views
    const handleRouteChange = (url: string) => {
      analytics.track('Page View', { url })
    }

    // Note: Implementation varies by platform
    // Web: Use Next.js router events
    // Native: Use Expo Router navigation events

    return () => {
      // Cleanup
    }
  }, [router])

  return children
}
```

## Deep Linking

### Configure Deep Links (Native)

```json
// apps/expo/app.json
{
  "expo": {
    "scheme": "myapp",
    "web": {
      "bundler": "metro"
    }
  }
}
```

**Universal links (iOS):**
```json
{
  "expo": {
    "ios": {
      "associatedDomains": ["applinks:myapp.com"]
    }
  }
}
```

**App links (Android):**
```json
{
  "expo": {
    "android": {
      "intentFilters": [
        {
          "action": "VIEW",
          "data": [
            {
              "scheme": "https",
              "host": "myapp.com"
            }
          ],
          "category": ["BROWSABLE", "DEFAULT"]
        }
      ]
    }
  }
}
```

### Handle Deep Links

```tsx
// packages/app/provider/deep-link-handler.tsx
import { useEffect } from 'react'
import { useRouter } from 'solito/router'
import * as Linking from 'expo-linking'

export function DeepLinkHandler({ children }) {
  const router = useRouter()

  useEffect(() => {
    // Handle initial URL (app opened from deep link)
    Linking.getInitialURL().then((url) => {
      if (url) {
        const { path, queryParams } = Linking.parse(url)
        router.push({ pathname: path, query: queryParams })
      }
    })

    // Handle URL changes (app already open)
    const subscription = Linking.addEventListener('url', ({ url }) => {
      const { path, queryParams } = Linking.parse(url)
      router.push({ pathname: path, query: queryParams })
    })

    return () => subscription.remove()
  }, [router])

  return children
}
```

## Prefetching

**Prefetch routes for better performance:**

```tsx
import { useLinkTo } from 'solito/router'

export function PostCard({ post }) {
  const linkTo = useLinkTo()

  const handlePrefetch = () => {
    // Prefetch the route
    linkTo({ pathname: `/post/${post.id}`, shallow: true })
  }

  return (
    <Link
      href={`/post/${post.id}`}
      onHoverIn={handlePrefetch} // Web: hover
      onPressIn={handlePrefetch}  // Native: touch start
    >
      <Text>{post.title}</Text>
    </Link>
  )
}
```

## Common Patterns

### Back Button with Fallback

```tsx
import { useRouter } from 'solito/router'

export function BackButton() {
  const router = useRouter()

  const handleBack = () => {
    // Go back if history exists, otherwise go home
    if (window.history.length > 1) {
      router.back()
    } else {
      router.push('/')
    }
  }

  return <Button onPress={handleBack}>Back</Button>
}
```

### Conditional Navigation

```tsx
const router = useRouter()

const handleSubmit = async () => {
  const success = await saveData()

  if (success) {
    router.push('/success')
  } else {
    router.push('/error')
  }
}
```

### Navigation with Confirmation

```tsx
import { Alert } from 'react-native'

const handleNavigate = () => {
  Alert.alert(
    'Unsaved Changes',
    'You have unsaved changes. Discard them?',
    [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Discard', onPress: () => router.push('/home') },
    ]
  )
}
```

## Type-Safe Routing

**Define route types:**

```tsx
// packages/app/navigation/types.ts
export type RootStackParamList = {
  '/': undefined
  '/profile': undefined
  '/user/[id]': { id: string }
  '/post/[category]/[slug]': { category: string; slug: string }
  '/search': { q?: string; sort?: 'newest' | 'oldest' }
}
```

**Use with type safety:**

```tsx
import { useParams } from 'solito/router'
import type { RootStackParamList } from 'app/navigation/types'

export function UserDetailScreen() {
  const params = useParams<RootStackParamList['/user/[id]']>()
  // params.id is typed as string ✅

  return <Text>User: {params.id}</Text>
}
```

## Best Practices

1. **Use relative paths** - `/profile` not `https://myapp.com/profile`
2. **Avoid navigation state** - Use query params or global state instead
3. **Type your routes** - Create type definitions for all routes
4. **Test on both platforms** - Navigation behavior can differ
5. **Use replace for auth flows** - Prevent back navigation to login
6. **Prefetch important routes** - Improve perceived performance
7. **Handle deep links** - Support universal links and app links
8. **Guard protected routes** - Redirect unauthenticated users
9. **Use Expo Router layouts** - For native tab and stack navigation
10. **Keep navigation logic in shared code** - Maximize code reuse

---

**Remember:** Solito navigation should feel native on both platforms while sharing as much code as possible. Always use `solito/link` and `solito/router` instead of platform-specific navigation libraries.
