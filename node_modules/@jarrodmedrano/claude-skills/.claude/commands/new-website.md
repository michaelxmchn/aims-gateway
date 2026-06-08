# New Website Project

**Trigger**: `/new-website [project-name]`

**Description**: Creates a new modern web development project with your choice of framework

---

When this skill is invoked:

1. Ask the user which framework they want to use:
   - Next.js (App Router with TypeScript)
   - React + Vite (TypeScript)
   - Vue 3 + Vite (TypeScript)
   - Vanilla (HTML/CSS/JS with Vite)

2. Extract the project name from the args, or ask if not provided

3. Create the project in the current directory using the appropriate command:
   - Next.js: `npx create-next-app@latest {project-name} --typescript --tailwind --app --no-src-dir --import-alias "@/*"`
   - React + Vite: `npm create vite@latest {project-name} -- --template react-ts`
   - Vue 3 + Vite: `npm create vite@latest {project-name} -- --template vue-ts`
   - Vanilla: `npm create vite@latest {project-name} -- --template vanilla-ts`

4. Navigate into the project directory

5. Install dependencies: `npm install`

6. Ask if they want to add any common packages:
   - UI Libraries: shadcn/ui, Material-UI, Chakra UI
   - State Management: Zustand, Redux Toolkit, TanStack Query
   - Utilities: axios, date-fns, zod, react-hook-form

7. Initialize git repository if not already initialized

8. Create a basic README with project info and getting started instructions

9. Show the user how to start the dev server

**Example usage**:
- `/new-website my-portfolio`
- `/new-website` (will prompt for name)
