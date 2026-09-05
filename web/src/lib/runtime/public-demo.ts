export function isPublicDemoMode(): boolean {
  return import.meta.env.VITE_PUBLIC_DEMO === "true";
}
