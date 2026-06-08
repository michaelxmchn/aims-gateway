# New Full-Stack Project

**Trigger**: `/new-fullstack [project-name]`

**Description**: Creates a new full-stack web application with frontend and backend

---

When this skill is invoked:

1. Ask the user which full-stack setup they want:
   - Next.js (App Router + API Routes + TypeScript)
   - T3 Stack (Next.js + tRPC + Prisma + Tailwind)
   - MERN (MongoDB + Express + React + Node)
   - Monorepo (React frontend + Express backend + shared types)
   - Solito (Expo + Next.js + shared navigation - Universal app for web + mobile)

2. Extract the project name from args, or ask if not provided

3. Create the project based on choice:

   **Next.js Full-Stack**:
   - `npx create-next-app@latest {project-name} --typescript --tailwind --app`
   - Add API route examples
   - Set up database connection (ask which: Prisma, MongoDB, PostgreSQL)

   **T3 Stack**:
   - `npm create t3-app@latest {project-name}`
   - Follow T3 setup prompts

   **MERN**:
   - Create root directory with client/ and server/ subdirectories
   - Client: React + Vite + TypeScript
   - Server: Express + TypeScript + MongoDB
   - Set up proxy configuration

   **Monorepo**:
   - Create monorepo structure:
     ```
     {project-name}/
       apps/
         frontend/    (React + Vite)
         backend/     (Express)
       packages/
         shared/      (shared TypeScript types)
       package.json   (workspace config)
     ```
   - Set up npm workspaces or pnpm workspace

   **Solito (Universal App)**:
   - Ask follow-up questions:
     * Package manager? (pnpm recommended, yarn, npm)
     * Include NativeWind? (Tailwind for React Native)
     * Include authentication? (Clerk, Supabase, custom, skip)
     * Include API layer? (tRPC, REST, skip)
     * Include UI library? (Tamagui, React Native Paper, custom, skip)

   - Use Solito starter template:
     ```bash
     npx create-solito-app@latest {project-name}
     ```
     Or create manually if custom setup needed

   - Create monorepo structure:
     ```
     {project-name}/
       apps/
         expo/              # React Native mobile app
           app/             # Expo Router file-system routes
           package.json
           app.json
         next/              # Next.js web app
           app/             # Next.js App Router
           public/
           package.json
           next.config.js
       packages/
         app/               # Shared UI and navigation
           features/        # Feature screens
           components/      # Reusable components
           lib/            # Utilities
           provider/       # Navigation provider
           package.json
         api/              # Shared API client (if selected)
           package.json
       package.json        # Root workspace config
       pnpm-workspace.yaml # or yarn/npm workspace
       turbo.json         # Turborepo config
     ```

   - Configure based on selections:
     * **NativeWind**: Set up Tailwind config, Metro config, Babel plugin
     * **Clerk**: Install @clerk/clerk-expo and @clerk/nextjs, configure providers
     * **Supabase**: Install @supabase/supabase-js, set up client
     * **tRPC**: Configure tRPC client, create example router
     * **Tamagui**: Install and configure Tamagui for universal styling

   - Add example screens:
     * Home screen (apps/expo/app/index.tsx and apps/next/app/page.tsx)
     * Profile screen with navigation
     * Demonstrate shared navigation with solito/link

   - Configure Metro bundler to watch monorepo
   - Set up TypeScript path aliases
   - Create .env.example for both platforms (NEXT_PUBLIC_ and EXPO_PUBLIC_)

   - Add development scripts to root package.json:
     ```json
     {
       "scripts": {
         "dev": "turbo run dev",
         "dev:next": "pnpm --filter next-app dev",
         "dev:expo": "pnpm --filter expo-app start",
         "build": "turbo run build",
         "lint": "turbo run lint",
         "typecheck": "turbo run typecheck"
       }
     }
     ```

   - Create README with:
     * Project structure explanation
     * Setup instructions (pnpm install)
     * How to run web app (cd apps/next && pnpm dev)
     * How to run mobile app (cd apps/expo && pnpm start)
     * Shared code location (packages/app)
     * Platform-specific code guidelines
     * Deployment instructions (Vercel for web, EAS for mobile)

4. Set up database and ORM:
   - Create database schema/models
   - Set up migration scripts
   - Add seed data scripts

5. Create authentication setup:
   - JWT or session-based auth
   - Login/register endpoints
   - Protected routes/middleware

6. Add common configuration:
   - Environment variables (.env.example)
   - CORS configuration
   - Error handling
   - Logging setup

7. Initialize git repository with appropriate .gitignore

8. Create README with:
   - Project structure
   - Setup instructions
   - Development commands
   - Environment variables needed

**Example usage**:
- `/new-fullstack my-saas-app`
- `/new-fullstack` (will prompt for name)

**Note**: For Solito projects, automatically invoke the `solito` skill after project creation to provide specialized guidance for cross-platform development, navigation patterns, and best practices.
