terraform {
  required_version = "~> 1.13.0"

  required_providers {
    proxmox = {
      source  = "bpg/proxmox"
      version = "0.120.0"
    }
  }

  # The state can hold secrets, so it stays outside the repo and is encrypted.
  # tofu/run.sh sets the path from HOMELAB_PRIVATE_DIR.
  backend "local" {}

  encryption {
    key_provider "pbkdf2" "state" {
      passphrase = var.state_passphrase
    }
    method "aes_gcm" "state" {
      keys = key_provider.pbkdf2.state
    }
    state {
      method   = method.aes_gcm.state
      enforced = true
    }
    plan {
      method   = method.aes_gcm.state
      enforced = true
    }
  }
}

locals {
  inventory = yamldecode(file("${path.module}/../inventory/hosts.yml")).all.children
  lan       = yamldecode(file("${path.module}/../inventory/group_vars/all.yml"))
  proxmox   = local.inventory.proxmox.hosts

  # The Debian VMs. The dns group is LXC and Home Assistant is HAOS, so they are not here.
  # A guest is provisioned once the inventory gives it a size.
  vms = merge([
    for group in ["edge", "swarm_managers"] : {
      for name, host in local.inventory.debian_guests.children[group].hosts : name => host if can(host.cores)
    }
  ]...)

  image_nodes = toset([for host in values(local.vms) : host.pve_node])
  image_url   = "https://cloud.debian.org/images/cloud/trixie/20261021-2638/debian-13-generic-amd64-20261021-2638.qcow2"
  image_sha   = "70ef6adc1c16155f8d575731b37d0f976d1c60b6144ac3f57914a3f4b30b202b69584d5d143aa39da0f0fe81df9e5b698909c0d94c7d91c6f6c4bb6581ead5f0"
}

provider "proxmox" {
  endpoint = "https://${local.proxmox.pve01.ansible_host}:8006/"
  insecure = true # Proxmox uses its own self-signed certificate.

  # The token comes from PROXMOX_VE_API_TOKEN. SSH is only for the Cloud-Init upload.
  ssh {
    username = "root"

    dynamic "node" {
      for_each = local.proxmox
      content {
        name    = node.key
        address = node.value.ansible_host
      }
    }
  }
}

# Each node needs its own copy: there is no shared storage.
resource "proxmox_download_file" "debian_image" {
  for_each = local.image_nodes

  node_name          = each.value
  datastore_id       = "local"
  content_type       = "import"
  url                = local.image_url
  checksum           = local.image_sha
  checksum_algorithm = "sha512"
}

resource "proxmox_virtual_environment_file" "user_data" {
  for_each = local.vms

  node_name    = each.value.pve_node
  datastore_id = "local"
  content_type = "snippets"

  source_raw {
    file_name = "${each.key}-user-data.yaml"
    data = templatefile("${path.module}/user-data.yaml.tftpl", {
      hostname      = each.key
      password_hash = var.john_password_hash
    })
  }
}

resource "proxmox_virtual_environment_vm" "guest" {
  for_each = local.vms

  name          = each.key
  node_name     = each.value.pve_node
  vm_id         = each.value.vmid
  on_boot       = true
  scsi_hardware = "virtio-scsi-single"

  agent {
    enabled = true
  }

  cpu {
    cores = each.value.cores
    type  = "x86-64-v2-AES"
  }

  memory {
    dedicated = each.value.memory_mb
  }

  disk {
    datastore_id = "local-lvm"
    import_from  = proxmox_download_file.debian_image[each.value.pve_node].id
    interface    = "scsi0"
    size         = each.value.disk_gb
    discard      = "on"
    iothread     = true
  }

  initialization {
    datastore_id      = "local-lvm"
    user_data_file_id = proxmox_virtual_environment_file.user_data[each.key].id

    dns {
      servers = local.lan.guest_dns_servers
    }

    ip_config {
      ipv4 {
        address = "${each.value.ansible_host}/24"
        gateway = local.lan.lan_gateway
      }
    }
  }

  network_device {
    bridge   = "vmbr0"
    firewall = false
  }

  operating_system {
    type = "l26"
  }
}
