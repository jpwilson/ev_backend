import { Langfuse } from "langfuse";

let _client: Langfuse | null = null;

export function getLangfuse(): Langfuse | null {
  if (_client) return _client;
  const publicKey = process.env.LANGFUSE_PUBLIC_KEY;
  const secretKey = process.env.LANGFUSE_SECRET_KEY;
  if (!publicKey || !secretKey) return null;
  _client = new Langfuse({
    publicKey,
    secretKey,
    baseUrl: process.env.LANGFUSE_HOST || "https://cloud.langfuse.com",
  });
  return _client;
}
