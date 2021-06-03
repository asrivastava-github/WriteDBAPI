variable cidr_blocks    {default = ""}
variable source_sg_id   {default = ""}
variable type           {}
variable to_port        {}
variable from_port      {}
variable protocol       {}
variable sg_count       {}
variable cidr_count     {}
variable sg_id          {}
variable description    {}

resource "aws_security_group_rule" "cidr_sg_rule" {
  count             = var.cidr_count
  from_port         = var.from_port
  protocol          = var.protocol
  security_group_id = var.sg_id
  cidr_blocks       = var.cidr_blocks
  to_port           = var.to_port
  type              = var.type
  description       = var.description
}

resource "aws_security_group_rule" "sg_rule" {
  count                    = var.sg_count
  from_port                = var.from_port
  protocol                 = var.protocol
  security_group_id        = var.sg_id
  source_security_group_id = var.source_sg_id
  to_port                  = var.to_port
  type                     = var.type
  description              = var.description
}