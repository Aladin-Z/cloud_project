#defining the provider block
provider "aws" {
  region = "us-east-1"
  profile = "default"
	
}

data "aws_vpc" "default" {
  default = true
}

# aws security security group 
resource "aws_security_group" "allow_tlss" {
  name        = "allow_tlss"
  description = "Allow TLS inbound traffic"
  

  ingress {
    description      = "TLS from VPC"
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]

  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }
  vpc_id = data.aws_vpc.default.id


  tags = {
    Name = "allow_tlss"
  }
}


data "aws_subnet_ids" "all" {
  vpc_id = data.aws_vpc.default.id
}

# generate a ssh key
resource "tls_private_key" "generated_ssh" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

# create key pair on aws (initially no keys exist because lab is reset every 4 hours)
resource "aws_key_pair" "generated_key" {
  key_name   = "generated_key"
  public_key = tls_private_key.generated_ssh.public_key_openssh
}

resource "local_file" "ssh_key" {
  filename = "generated_key.pem"
  content = tls_private_key.generated_ssh.private_key_pem
}

resource "null_resource" "key_move" {
    provisioner "local-exec" { 
      command = "cp generated_key.pem ~/.ssh/generated_key.pem &&  chmod 400 ~/.ssh/generated_key.pem" 
  }
  depends_on = [local_file.ssh_key]
}


# Create instances 
resource "aws_instance" "web-1" {
    ami           = "ami-08c40ec9ead489470"
    instance_type = "t2.micro"
    count = 2
    key_name = aws_key_pair.generated_key.key_name
    vpc_security_group_ids = ["${aws_security_group.allow_tlss.id}"]
    timeouts {
      create= "1h30m"
      update= "2h"
      delete= "20m"
    }

    # retry connection until host is ready before starting ansible (if we dont do this ansible will timeout if it tries to connect before host is ready)
    provisioner "remote-exec" {
      inline = ["ls"]
    }
    connection {
      host        = self.public_ip
      agent       = false
      type        = "ssh"
      user        = "ubuntu"
      timeout = "2m"
      private_key = tls_private_key.generated_ssh.private_key_pem
    }
    subnet_id = element(tolist(data.aws_subnet_ids.all.ids), 0)
    depends_on = [null_resource.key_move]
    provisioner "local-exec" { 
    command = "ANSIBLE_HOST_KEY_CHECKING=False ansible-playbook -i '${self.public_ip},' -u ubuntu --private-key ~/.ssh/generated_key.pem  ${path.module}/instance.ansible.yml" 
  }
}