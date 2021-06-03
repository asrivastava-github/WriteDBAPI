variable name             {}
variable handler          {}
variable iam_role         {}
variable db_table         {}
variable methods          {}
variable runtime          {default = "python3.8"}
variable port             {default = 80}
variable source_code      {}
variable endpoint         {}
variable tf_region        {}


data aws_vpcs avi_vpc {
  tags = {
    Name = "avi-vpc"
  }
}

data "aws_subnet" "private_subnet_0" {
  filter {
    name   = "tag:Name"
    values = ["avi-private-subnet_0"]
  }
}

data "aws_subnet" "private_subnet_1" {
  filter {
    name   = "tag:Name"
    values = ["avi-private-subnet_1"]
  }
}

data "aws_security_groups" "private_sg" {
  tags = {
    Name = "avi-public-alb-sec-grp"
  }
}

locals {
  endpoint = replace(var.endpoint, "/", "")
}

resource "aws_lambda_function" "write_api" {
  filename         = var.source_code
  source_code_hash = filebase64sha256(var.source_code)
  function_name    = var.name
  handler          = var.handler
  role             = var.iam_role
  runtime          = var.runtime
  timeout          = 60
  memory_size      = 128
  vpc_config {
    security_group_ids = data.aws_security_groups.private_sg.ids
    subnet_ids         = [data.aws_subnet.private_subnet_0.id, data.aws_subnet.private_subnet_1.id]
  }
  environment {
    variables  = {
      DB_TABLE   = var.db_table
      PATH       = var.endpoint
      METHODS    = var.methods
      REGION = var.tf_region
    }
  }
}

resource "aws_lb_target_group" "tg" {
  name        = "avi-${local.endpoint}-tg"
  port        = 80
  protocol    = "HTTP"
  vpc_id      = data.aws_vpcs.avi_vpc.id
  target_type = "lambda"
  stickiness {
    type            = "lb_cookie"
    cookie_duration = "3000"
  }
  health_check {
    healthy_threshold   = 3
    unhealthy_threshold = 5
    protocol            = "HTTP"
    interval            = 30
    timeout             = 5
    path                = "/health"
    matcher             = "200"
  }
  tags = {
    Name = "avi-${local.endpoint}-tg"
  }
}

data "aws_lb" "lb" {
  name = "avi-app-alb"
}

resource "aws_lb_listener" "lb_listener" {
  load_balancer_arn = data.aws_lb.lb.arn
  port              = 80
  # certificate_arn = var.cert_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }
}

resource "aws_alb_listener_rule" "listener_rule" {
  listener_arn = aws_lb_listener.lb_listener.arn
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.tg.arn
  }
  condition {
    path_pattern {
      values = [var.endpoint]
    }
  }
}

resource "aws_lambda_permission" "alb-permission" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.write_api.function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.tg.arn
}

resource "aws_lb_target_group_attachment" "attach-lambda" {
  target_group_arn = aws_lb_target_group.tg.arn
  target_id        = aws_lambda_function.write_api.arn

  depends_on = [
    aws_lambda_permission.alb-permission
  ]
}


