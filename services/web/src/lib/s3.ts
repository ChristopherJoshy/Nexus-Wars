import { S3Client, GetObjectCommand, PutObjectCommand } from "@aws-sdk/client-s3";

// S3/MinIO client for the web app (used by submissions and replays API).

let _client: S3Client | null = null;

export function getS3(): S3Client | null {
  const endpoint = process.env.S3_ENDPOINT;
  if (!endpoint) return null;
  if (!_client) {
    _client = new S3Client({
      endpoint,
      region: process.env.S3_REGION || "us-east-1",
      credentials: {
        accessKeyId: process.env.S3_ACCESS_KEY || "nexus",
        secretAccessKey: process.env.S3_SECRET_KEY || "nexusnexus",
      },
      forcePathStyle: true,
    });
  }
  return _client;
}

export const S3_BUCKET = process.env.S3_BUCKET || "nexus-replays";

export { GetObjectCommand, PutObjectCommand };
