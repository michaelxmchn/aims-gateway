# New Backend Project

**Trigger**: `/new-backend [project-name]`

**Description**: Creates a new Node.js backend/API project

---

When this skill is invoked:

1. Ask the user which backend setup they want:
   - Express.js + TypeScript
   - Fastify + TypeScript
   - NestJS (opinionated, batteries-included)
   - Hono (lightweight, edge-ready)

2. Extract the project name from args, or ask if not provided

3. Create the project directory: `mkdir {project-name} && cd {project-name}`

4. Initialize the project based on choice:

   **Express.js**:
   - `npm init -y`
   - Install: `npm install express cors dotenv`
   - Install dev: `npm install -D typescript @types/node @types/express @types/cors ts-node-dev nodemon`
   - Create tsconfig.json
   - Create basic Express server with TypeScript

   **Fastify**:
   - `npm init -y`
   - Install: `npm install fastify @fastify/cors dotenv`
   - Install dev: `npm install -D typescript @types/node ts-node-dev`
   - Create tsconfig.json
   - Create basic Fastify server

   **NestJS**:
   - `npx @nestjs/cli new {project-name} --package-manager npm`

   **Hono**:
   - `npm init -y`
   - Install: `npm install hono`
   - Install dev: `npm install -D typescript @types/node tsx`
   - Create basic Hono server

5. Create project structure:
   ```
   src/
     index.ts (or main.ts)
     routes/
     controllers/
     services/
     middleware/
     types/
   ```

6. Add npm scripts to package.json:
   - `dev`: Development server with hot reload
   - `build`: TypeScript compilation
   - `start`: Production server

7. Create `.env.example` with common variables

8. Create `.gitignore` (node_modules, .env, dist)

9. Initialize git repository

10. Ask if they want to add:
    - Database: PostgreSQL (pg), MongoDB (mongoose), Prisma ORM
    - Authentication: JWT setup, Passport.js
    - Validation: Zod, Joi
    - Testing: Jest, Vitest

**Example usage**:
- `/new-backend my-api`
- `/new-backend` (will prompt for name)
