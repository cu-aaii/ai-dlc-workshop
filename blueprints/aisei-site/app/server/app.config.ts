export interface EnvVars {
  PORT?: string;
}

const requiredEnvVars: (keyof EnvVars)[] = [];

const typedEnv = process.env as unknown as EnvVars;

requiredEnvVars.forEach((key) => {
  if (!typedEnv[key]) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
});

export const config = {
  port: Number(typedEnv.PORT ?? 4300),
} as const;
