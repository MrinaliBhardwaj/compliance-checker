variable "region" {
  description = "Every managed service is pinned here. Data residency is a contractual claim to an RBI-regulated buyer, so this is not a knob to change casually."
  type        = string
  default     = "ap-south-1"

  validation {
    condition     = startswith(var.region, "ap-south-")
    error_message = "Regis data must stay in India. Only ap-south-* regions are permitted."
  }
}

variable "env" {
  description = "dev | staging | prod"
  type        = string

  validation {
    condition     = contains(["dev", "staging", "prod"], var.env)
    error_message = "env must be dev, staging or prod."
  }
}

variable "vpc_id" {
  description = "Existing VPC to attach to."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for RDS and ElastiCache. At least two AZs."
  type        = list(string)

  validation {
    condition     = length(var.private_subnet_ids) >= 2
    error_message = "RDS and ElastiCache subnet groups need at least two subnets."
  }
}

variable "app_security_group_id" {
  description = "Security group of the API/worker tasks — the only ingress allowed to the datastores."
  type        = string
}

variable "db_instance_class" {
  type    = string
  default = "db.t4g.micro"
}

variable "db_allocated_storage_gb" {
  type    = number
  default = 20
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.micro"
}
