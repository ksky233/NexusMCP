import type { CreateClientConfig } from "@/generated/api/client.gen";

export const createClientConfig: CreateClientConfig = (config) => ({
  ...config,
  // 运行时根据当前 Origin 计算 Same-Origin Admin 地址；Artifact 不绑定部署 Host。
  baseUrl: new URL("/admin", globalThis.location?.origin ?? "http://localhost").toString(),
});
