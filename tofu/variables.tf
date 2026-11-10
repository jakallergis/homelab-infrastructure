variable "john_password_hash" {
  description = "Password hash for the user john. tofu/run.sh reads it from secrets/guests.yml."
  type        = string
  sensitive   = true
}

variable "state_passphrase" {
  description = "Passphrase that encrypts the state. It comes from secrets/tofu.env."
  type        = string
  sensitive   = true
}
