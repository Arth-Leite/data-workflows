variable "project_id" {
  type    = string
  default = "dataops-case-study-509018"
}

variable "region" {
  type    = string
  default = "europe-west1"
}

variable "my_ip" {
  type        = string
  description = "My public IP as a CIDR block"

  validation {
    condition     = can(cidrnetmask(var.my_ip))
    error_message = "my_ip must be a CIDR block"
  }
}
