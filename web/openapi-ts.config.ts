import { defineConfig } from "@hey-api/openapi-ts";

export default defineConfig({
  input: "../contracts/admin.openapi.json",
  output: {
    path: "src/generated/api",
    postProcess: [],
  },
  plugins: [
    "@hey-api/typescript",
    {
      name: "@hey-api/sdk",
      validator: {
        request: false,
        response: "zod",
      },
    },
    {
      name: "zod",
      compatibilityVersion: 4,
      requests: false,
      responses: true,
    },
    {
      name: "@hey-api/client-fetch",
      runtimeConfigPath: "./src/lib/api/hey-api-runtime.ts",
    },
  ],
});
