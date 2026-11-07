// Expo injects EXPO_PUBLIC_* env vars at bundle time via `process.env`.
// This ambient declaration keeps `tsc --noEmit` happy without @types/node.
declare const process: {
  env: Record<string, string | undefined>;
};
