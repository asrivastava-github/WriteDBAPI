variable sg_name      {}
variable vpc_id       {}
variable description  {}

resource "aws_security_group" "sg" {
  name        = var.sg_name
  vpc_id      = var.vpc_id
  description = var.description
  tags        = {
    Name      = var.sg_name
  }
}

output "sg_id" {
  value = aws_security_group.sg.id
}