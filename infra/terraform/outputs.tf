output "database_secret_arn" {
  description = "Secrets Manager ARN holding the RDS master credentials. Compose REGIS_DATABASE_URL from this at boot; never bake it into an image."
  value       = aws_db_instance.regis.master_user_secret[0].secret_arn
}

output "database_endpoint" {
  value = aws_db_instance.regis.endpoint
}

output "redis_endpoint" {
  description = "Use with rediss:// — transit encryption is on."
  value       = aws_elasticache_replication_group.regis.primary_endpoint_address
}

output "evidence_bucket" {
  value = aws_s3_bucket.evidence.id
}

output "kms_key_arn" {
  value = aws_kms_key.regis.arn
}
