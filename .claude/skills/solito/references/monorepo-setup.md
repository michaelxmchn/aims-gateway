# Monorepo Setup for Solito Projects

This guide covers workspace configuration, package structure, dependency management, and build tooling for Solito monorepos.

## Monorepo Structure

### Recommended Structure

```
my-app/
  apps/
    expo/                  # React Native mobile app
      app/                 # Expo Router file-system routes
      package.json
      app.json
      tsconfig.json
    next/                  # Next.js web app
      app/                 # Next.js App Router
      public/
      package.json
      next.config.js
      tsconfig.json
  packages/
    app/                   # Shared UI and navigation
      features/            # Feature-based screens
      components/          # Reusable components
      lib/                 # Utilities and helpers
      provider/            # Navigation and context providers
      package.json
      tsconfig.json
    api/                   # Shared API client (optional)
      client.ts
      types.ts
      package.json
    eslint-config/         # Shared ESLint config (optional)
    typescript-config/     # Shared tsconfig (optional)
  package.json             # Root workspace configuration
  pnpm-workspace.yaml      # pnpm workspace config
  turbo.json               # Turborepo config (optional)
  .gitignore
  README.md
```

## Package Manager Setup

### pnpm (Recommended)

**Why pnpm?**
- Fastest monorepo support
- Efficient disk space usage (symlinks)
- Strict dependency resolution prevents phantom dependencies

**Install pnpm:**
```bash
npm install -g pnpm
```

**Root package.json:**
```json
{
  "name": "my-app",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build",
    "lint": "turbo run lint",
    "typecheck": "turbo run typecheck",
    "clean": "turbo run clean && rm -rf node_modules"
  },
  "devDependencies": {
    "turbo": "^2.0.0",
    "typescript": "^5.3.0"
  }
}
```

**pnpm-workspace.yaml:**
```yaml
packages:
  - 'apps/*'
  - 'packages/*'
```

**Install dependencies:**
```bash
pnpm install
```

### Yarn Workspaces

**Root package.json:**
```json
{
  "name": "my-app",
  "private": true,
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build"
  }
}
```

**Install dependencies:**
```bash
yarn install
```

### npm Workspaces

**Root package.json:**
```json
{
  "name": "my-app",
  "private": true,
  "workspaces": [
    "apps/*",
    "packages/*"
  ],
  "scripts": {
    "dev": "turbo run dev",
    "build": "turbo run build"
  }
}
```

**Install dependencies:**
```bash
npm install
```

## Package Configurations

### packages/app/package.json

```json
{
  "name": "app",
  "version": "1.0.0",
  "main": "index.ts",
  "types": "index.ts",
  "dependencies": {
    "react": "^18.2.0",
    "react-native": "^0.73.0",
    "solito": "^4.0.0",
    "nativewind": "^4.0.0",
    "zustand": "^4.4.0"
  },
  "devDependencies": {
    "@types/react": "^18.2.0",
    "typescript": "^5.3.0"
  }
}
```

### apps/next/package.json

```json
{
  "name": "next-app",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "app": "workspace:*",
    "next": "^14.1.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-native-web": "^0.19.0"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "@types/react": "^18.2.0",
    "typescript": "^5.3.0",
    "tailwindcss": "^3.4.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0"
  }
}
```

**Key points:**
- Use `workspace:*` to reference local packages
- Shared dependencies (react, react-native) should match versions

### apps/expo/package.json

```json
{
  "name": "expo-app",
  "version": "1.0.0",
  "private": true,
  "main": "index.js",
  "scripts": {
    "start": "expo start",
    "android": "expo start --android",
    "ios": "expo start --ios",
    "web": "expo start --web",
    "lint": "eslint .",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "app": "workspace:*",
    "expo": "^50.0.0",
    "expo-router": "^3.4.0",
    "react": "^18.2.0",
    "react-native": "^0.73.0",
    "react-native-safe-area-context": "^4.8.0",
    "react-native-screens": "^3.29.0",
    "nativewind": "^4.0.0"
  },
  "devDependencies": {
    "@babel/core": "^7.23.0",
    "@types/react": "^18.2.0",
    "typescript": "^5.3.0"
  }
}
```

## Turborepo Configuration

**turbo.json:**
```json
{
  "$schema": "https://turbo.build/schema.json",
  "pipeline": {
    "dev": {
      "cache": false,
      "persistent": true
    },
    "build": {
      "dependsOn": ["^build"],
      "outputs": [".next/**", "dist/**", ".expo/**"]
    },
    "lint": {
      "dependsOn": ["^lint"]
    },
    "typecheck": {
      "dependsOn": ["^typecheck"]
    },
    "clean": {
      "cache": false
    }
  }
}
```

**Benefits:**
- Parallel task execution
- Intelligent caching
- Dependency graph awareness
- Faster builds and development

## TypeScript Configuration

### Root tsconfig.json

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["ES2020"],
    "module": "commonjs",
    "moduleResolution": "node",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true
  }
}
```

### packages/app/tsconfig.json

```json
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "jsx": "react-native",
    "baseUrl": ".",
    "paths": {
      "app/*": ["./*"]
    }
  },
  "include": [
    "**/*.ts",
    "**/*.tsx"
  ],
  "exclude": [
    "node_modules"
  ]
}
```

### apps/next/tsconfig.json

```json
{
  "extends": "../../tsconfig.json",
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "jsx": "preserve",
    "module": "esnext",
    "moduleResolution": "bundler",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts"
  ],
  "exclude": [
    "node_modules"
  ]
}
```

### apps/expo/tsconfig.json

```json
{
  "extends": "expo/tsconfig.base",
  "compilerOptions": {
    "strict": true,
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": [
    "**/*.ts",
    "**/*.tsx"
  ]
}
```

## Dependency Management

### Installing Dependencies

**Root dependencies:**
```bash
pnpm add -D <package> -w
```

**Workspace package dependencies:**
```bash
# Add to specific workspace
pnpm add <package> --filter next-app

# Add to all workspaces
pnpm add <package> -r
```

**Local package references:**
```bash
# In apps/next/package.json
pnpm add app --filter next-app --workspace
```

### Version Synchronization

**Keep these versions in sync across all packages:**
- react
- react-native
- @types/react
- typescript

**Use a root package.json to enforce versions:**
```json
{
  "pnpm": {
    "overrides": {
      "react": "18.2.0",
      "react-native": "0.73.0",
      "@types/react": "18.2.0"
    }
  }
}
```

### Shared Dependencies

**Create shared dependency packages:**

```
packages/
  dependencies/
    package.json
```

```json
{
  "name": "dependencies",
  "version": "1.0.0",
  "dependencies": {
    "react": "^18.2.0",
    "react-native": "^0.73.0",
    "zustand": "^4.4.0"
  }
}
```

**Reference in other packages:**
```json
{
  "dependencies": {
    "dependencies": "workspace:*"
  }
}
```

## NativeWind Setup

### Install NativeWind

```bash
pnpm add nativewind tailwindcss --filter app
```

### packages/app/tailwind.config.js

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './features/**/*.{js,jsx,ts,tsx}',
    './components/**/*.{js,jsx,ts,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        primary: '#3B82F6',
        secondary: '#10B981',
      },
    },
  },
  plugins: [],
}
```

### apps/next/tailwind.config.js

```js
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './app/**/*.{js,ts,jsx,tsx}',
    '../../packages/app/**/*.{js,ts,jsx,tsx}',
  ],
  presets: [require('nativewind/preset')],
  theme: {
    extend: {},
  },
  plugins: [],
}
```

### apps/expo/metro.config.js

```js
const { getDefaultConfig } = require('expo/metro-config')
const path = require('path')

const projectRoot = __dirname
const workspaceRoot = path.resolve(projectRoot, '../..')

const config = getDefaultConfig(projectRoot)

// Watch all files in monorepo
config.watchFolders = [workspaceRoot]

// Support workspace packages
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
]

// NativeWind configuration
config.resolver.sourceExts.push('mjs')

module.exports = config
```

## Build Scripts

### Concurrent Development

**Run both apps simultaneously:**

```json
{
  "scripts": {
    "dev": "turbo run dev",
    "dev:next": "pnpm --filter next-app dev",
    "dev:expo": "pnpm --filter expo-app start"
  }
}
```

**Or use concurrently:**

```bash
pnpm add -D concurrently -w
```

```json
{
  "scripts": {
    "dev": "concurrently \"pnpm:dev:next\" \"pnpm:dev:expo\"",
    "dev:next": "pnpm --filter next-app dev",
    "dev:expo": "pnpm --filter expo-app start"
  }
}
```

### Production Builds

```json
{
  "scripts": {
    "build": "turbo run build",
    "build:next": "pnpm --filter next-app build",
    "build:expo": "pnpm --filter expo-app build"
  }
}
```

## Common Issues

### Dependency Resolution

**Phantom dependencies** - Package works locally but fails in CI:

```yaml
# pnpm-workspace.yaml
packages:
  - 'apps/*'
  - 'packages/*'

# .npmrc
auto-install-peers=true
strict-peer-dependencies=false
```

### Metro Bundler Issues

**Clear cache if you see import errors:**

```bash
# Expo
pnpm --filter expo-app start --clear

# Metro
pnpm --filter expo-app start --reset-cache
```

### TypeScript Path Resolution

**If TypeScript can't resolve `app/*` imports:**

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

### Hoisting Issues

**Some packages don't work when hoisted:**

```yaml
# .npmrc
shamefully-hoist=false
public-hoist-pattern[]=*eslint*
public-hoist-pattern[]=*prettier*
```

## Best Practices

1. **Use pnpm** - Best monorepo support and performance
2. **Enable Turborepo** - Faster builds with intelligent caching
3. **Sync versions** - Keep react/react-native versions in sync
4. **Use workspace protocol** - `workspace:*` for local packages
5. **Share configs** - Create shared ESLint, TypeScript, Prettier configs
6. **Clear caches** - When seeing import or build issues
7. **Document setup** - README with setup instructions for new developers
8. **Use path aliases** - Consistent import paths across packages
9. **Separate concerns** - Keep platform code in apps/, shared code in packages/
10. **Test locally** - Verify changes work on both platforms before committing

---

**Remember:** A well-configured monorepo enables efficient code sharing and keeps your web and native apps in sync. Invest time in proper setup to avoid issues later.
