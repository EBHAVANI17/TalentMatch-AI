class S3Storage:
    """Amazon S3 (or any S3-compatible store). Objects are private; downloads use presigned URLs."""

    name = "s3"

    def __init__(self, bucket: str, region: str = "", endpoint_url: str = "") -> None:
        import boto3  # imported lazily so local development doesn't need AWS libraries configured

        self.bucket = bucket
        self.client = boto3.client("s3", region_name=region or None, endpoint_url=endpoint_url or None)

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.client.put_object(
            Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256",
        )

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presigned_url(self, key: str, filename: str, content_type: str, expires_in: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": self.bucket,
                "Key": key,
                "ResponseContentType": content_type,
                "ResponseContentDisposition": f'attachment; filename="{filename}"',
            },
            ExpiresIn=expires_in,
        )
