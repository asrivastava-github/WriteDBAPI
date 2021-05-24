// Start of Variable section. Default values can be removed and fetched from tfvars file if needed
variable state_bucket         {default = "avi-assignment-api-service"}
variable state_key            {default = "avi-assignment-tfstate.tfstate"}
variable db_name              {default = "avi-app-dynamo"}
variable lambda_name          {default = "avi-lambda-app-api"}
variable dynamo_read          {default = 20}
variable dynamo_write         {default = 20}
variable cidr_block           {default = "10.0.0.0/24"}
variable private_subnet_cidr  {default = ["10.0.0.112/28", "10.0.0.144/28"]}
variable public_subnet_cidr   {default = ["10.0.0.32/28", "10.0.0.80/28"]}
variable dynamobAWSIps        {default = ["52.94.24.0/23", "52.94.26.0/23", "52.94.5.0/24", "52.119.240.0/21"]}
variable "availability_zone"  {default = ["eu-west-1a", "eu-west-1b"]}
variable ports                {default = [80, 443]}
variable internet             {default = "0.0.0.0/0"}
variable methods              {default = "GET"}
variable endpoint             {default = "/app"}
variable source_code          {}

// Start of Variable section.

// Remove the slash from endpoint and use a application name
locals {
  path = replace(var.endpoint, "/", "")
}


# Required terraform version and AWS region
terraform {
  required_version = ">=0.12"
  backend "s3" {
    region = "eu-west-1"
  }
}


# Required terraform provider, AWS in this case deploying the solution to AWS region eu-west-1
provider "aws" {
  region           = "eu-west-1"
}

# Start of Networking Section. It will carry VPC, VPC flow logs, IGW, Public Subnets, Routes, Route Tables, Route Table
# Association to subnets. NACLs and Rules to allow Internet connectivity to port 80 and 443 and outbound to ephemeral
# ports
resource "aws_vpc" "app_vpc" {
  cidr_block = var.cidr_block
  tags = {
    Name = "avi-vpc"
  }
}

resource "aws_flow_log" "vpc_flow_logs" {
  iam_role_arn    = aws_iam_role.vpc-logs-role.arn
  log_destination = aws_cloudwatch_log_group.vpc-logs.arn
  traffic_type    = "ALL"
  vpc_id          = aws_vpc.app_vpc.id
  depends_on      = [aws_cloudwatch_log_group.vpc-logs, aws_iam_role.vpc-logs-role]
}

resource "aws_cloudwatch_log_group" "vpc-logs" {
  name              = "vpc-flow-logs"
  retention_in_days = "14"
}

# IAM Access Control (Role and Policy) needed for VPC flow logs
resource "aws_iam_role" "vpc-logs-role" {
  name = "vpcFlowLogsAccess"
    assume_role_policy = <<EOF
{"Version": "2012-10-17",
  "Statement": [{
    "Sid": "vpcflowlogSTS",
    "Effect": "Allow",
    "Principal": {"Service": ["vpc-flow-logs.amazonaws.com"]},
    "Action": "sts:AssumeRole"}
  ]
}
EOF
}

resource "aws_iam_policy" "vpc_flow_logs_policy" {
  name   = "vpcFlowLogCreationPolicy"
  policy = file("infrastructure/policy/vpc_flow_logs_policy.json")
}

resource "aws_iam_policy_attachment" "attach_vpc_flow_log_policy" {
  name       = "vpcFlowLogCreation"
  policy_arn = aws_iam_policy.vpc_flow_logs_policy.arn
  roles      = [aws_iam_role.vpc-logs-role.name]
  depends_on = [aws_iam_role.vpc-logs-role]
}
# End of IAM Access Control

# Internet Gateway to allow internet Traffic inside VPC
resource "aws_internet_gateway" "gateway" {
  vpc_id = aws_vpc.app_vpc.id
  tags = {
    Name = "avi-gateway"
  }
  depends_on = [aws_vpc.app_vpc]
}


# Start Creation Public and Private Routes/Subnets/NACLs to way for request to reach to ALB and then Lambda
# Where ALB will reside
resource "aws_subnet" "public_subnet" {
  count             = length(var.public_subnet_cidr)
  cidr_block        = var.public_subnet_cidr[count.index]
  vpc_id            = aws_vpc.app_vpc.id
  availability_zone = var.availability_zone[count.index]
  tags = {
    Name = "avi-public-subnet_${count.index}"
  }
  depends_on = [aws_vpc.app_vpc]
}

# Where Lambda will reside
resource "aws_subnet" "private_subnet" {
  count             = length(var.private_subnet_cidr)
  cidr_block        = var.private_subnet_cidr[count.index]
  vpc_id            = aws_vpc.app_vpc.id
  availability_zone = var.availability_zone[count.index]
  tags = {
    Name = "avi-private-subnet_${count.index}"
  }
  depends_on = [aws_vpc.app_vpc]
}

# Create and attach a Network access control list to public subnet for traffic control
resource "aws_network_acl" "nacl_public" {
  vpc_id     = aws_vpc.app_vpc.id
  subnet_ids = aws_subnet.public_subnet.*.id
  tags = {
    Name = "avi-public-acl"
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.public_subnet]
}

# Create and attach a Network access control list to private subnet for traffic control
resource "aws_network_acl" "nacl_private" {
  vpc_id     = aws_vpc.app_vpc.id
  subnet_ids = aws_subnet.private_subnet.*.id
  tags = {
    Name = "avi-private-acl"
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.private_subnet]
}

# Allow request to get into the subnet on port 80 and 443 where ALB is listening
resource "aws_network_acl_rule" "public_nacl_rules_in_https" {
  count          = length(var.ports)
  network_acl_id = aws_network_acl.nacl_public.id
  protocol       = "tcp"
  rule_action    = "allow"
  rule_number    = count.index * 10 + 200
  cidr_block     = var.internet
  to_port        = var.ports[count.index]
  from_port      = var.ports[count.index]
  lifecycle {
    create_before_destroy = false
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.public_subnet]
}

# Provide a way for DynamoDB response to reach to lambda. Access to DynamoDB service ips list on ephemeral ports
resource "aws_network_acl_rule" "private_nacl_rules_in_dynamoDB_EP" {
  count          = length(var.dynamobAWSIps)
  network_acl_id = aws_network_acl.nacl_private.id
  protocol       = "tcp"
  rule_action    = "allow"
  rule_number    = count.index * 10 + 400
  cidr_block     = var.dynamobAWSIps[count.index]
  to_port        = 65535
  from_port      = 1024
  lifecycle {
    create_before_destroy = false
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.private_subnet, aws_vpc_endpoint.dynamoDB]
}

# Required for response to reach to internet
resource "aws_network_acl_rule" "public_nacl_rules_out_ephemeral" {
  network_acl_id = aws_network_acl.nacl_public.id
  protocol       = "tcp"
  rule_action    = "allow"
  rule_number    = 200
  cidr_block     = var.internet
  to_port        = 65535
  from_port      = 1024
  egress         = true
  lifecycle {
    create_before_destroy = false
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.public_subnet]
}

# Required for Lambda to connect to DynamoDB endpoint
resource "aws_network_acl_rule" "private_nacl_rules_out_https" {
  network_acl_id = aws_network_acl.nacl_private.id
  protocol       = "tcp"
  rule_action    = "allow"
  rule_number    = 200
  cidr_block     = var.internet
  to_port        = 443
  from_port      = 443
  egress         = true
  lifecycle {
    create_before_destroy = false
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.private_subnet]
}

# Public route table to attach to public subnet
resource "aws_route_table" "public_route_table" {
  vpc_id = aws_vpc.app_vpc.id
  tags = {
    Name = "avi-public-route-table"
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.public_subnet]
}

# Private route table to attach to public subnet
resource "aws_route_table" "private_route_table" {
  vpc_id = aws_vpc.app_vpc.id
  tags = {
    Name = "avi-private-route-table"
  }
  depends_on = [aws_vpc.app_vpc, aws_subnet.private_subnet]
}

# DynamoDB endpoint to serve the request within AWS network
resource "aws_vpc_endpoint" "dynamoDB" {
  vpc_id       = aws_vpc.app_vpc.id
  service_name = "com.amazonaws.eu-west-1.dynamodb"
  route_table_ids = [aws_route_table.private_route_table.id]
  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Sid       = "AccessDyDB",
      Effect    = "Allow",
      Principal = "*"
      Action    = "*"
      Resource  = "*"
    }]
  })
  depends_on = [aws_route_table.private_route_table]
  tags = {
    Name = "avi-dynamodb-ep"
  }
}

# Public route attached to public subnet will connect to internet gateway for internet connectivity and to know which subnet to land to
resource "aws_route" "public_routes" {
  route_table_id         = aws_route_table.public_route_table.id
  destination_cidr_block = var.internet
  gateway_id             = aws_internet_gateway.gateway.id
  depends_on = [aws_vpc.app_vpc, aws_subnet.public_subnet, aws_route_table.public_route_table]
}

# Attach public route table to public subnet
resource "aws_route_table_association" "public_route_table_association" {
  count          = length(var.public_subnet_cidr)
  route_table_id = aws_route_table.public_route_table.id
  subnet_id      = aws_subnet.public_subnet.*.id[count.index]
  depends_on     = [aws_vpc.app_vpc, aws_subnet.public_subnet, aws_route_table.public_route_table]
}

# Attach private route table to private subnet
resource "aws_route_table_association" "private_route_table_association" {
  count          = length(var.private_subnet_cidr)
  route_table_id = aws_route_table.private_route_table.id
  subnet_id      = aws_subnet.private_subnet.*.id[count.index]
  depends_on     = [aws_vpc.app_vpc, aws_subnet.private_subnet, aws_route_table.private_route_table]
}

# Start Public Routes/Subnets/NACLs to serve the external request
# End of Standard Networking Sections


# Start of Database layer which will carry DynamoDB. It fully AWS managed so sort and quick
# Create DynamoDB where timestamp needs to be written
resource "aws_dynamodb_table" "app_db" {
  name           = var.db_name
  billing_mode   = "PAY_PER_REQUEST"
  read_capacity  = 20
  write_capacity = 20
  hash_key       = "uniqueId"
  range_key      = "timeStamp"

  attribute {
    name = "uniqueId"
    type = "S"
  }

  attribute {
    name = "timeStamp"
    type = "S"
  }

//  point_in_time_recovery {
//    enabled = true
//  }
//  replica {
//    region_name  = "eu-west-2"
//  }
}

# End of DB layer


# Start of Business logic and Network Layer. It will carry ALB, Lambda, ALB/Lambda Security groups, ALB Listeners,
# Listener rules, Target groups, Target group attachment
# Create public security group to connect to ALB. We will define the rules below.
resource "aws_security_group" "public-alb-sg" {
  name        = "avi-public-alb-sec-grp"
  vpc_id      = aws_vpc.app_vpc.id
  description = "Security Group to allow connection to ALB"
  tags = {
    Name = "avi-public-alb-sec-grp"
  }
}

# Create public security group to connect to Lambda.
resource "aws_security_group" "private-lambda-sg" {
  name        = "avi-private-lambda-sec-grp"
  vpc_id      = aws_vpc.app_vpc.id
  description = "Security Group to allow connection to Lambda"
  tags = {
    Name = "avi-private-lambda-sec-grp"
  }
}

# Inbound Rules for alb security group on port 80 and 443 from internet, Since it's repetitive using module
module "alb_in" {
  source      = "./infrastructure/modules/security_group_rules"
  count       = length(var.ports)
  type        = "ingress"
  to_port     = var.ports[count.index]
  from_port   = var.ports[count.index]
  protocol    = "tcp"
  sg_count    = "0"
  cidr_count  = "1"
  cidr_blocks  = [var.internet]
  sg_id       = aws_security_group.public-alb-sg.id
  description = "ALB Inbound"
}

# Outbound Rules for alb security group on port 80 and 443 to Lambda, Since it's repetitive using module
module "alb_out_std" {
  source        = "./infrastructure/modules/security_group_rules"
  count         = length(var.ports)
  type          = "egress"
  to_port       = var.ports[count.index]
  from_port     = var.ports[count.index]
  protocol      = "tcp"
  sg_count      = "1"
  cidr_count    = "0"
  source_sg_id  = aws_security_group.private-lambda-sg.id
  sg_id         = aws_security_group.public-alb-sg.id
  description   = "ALB outbound"
}

# Outbound Rules for alb security group on ephemeral ports to internet.
module "alb_out_ephemral" {
  source        = "./infrastructure/modules/security_group_rules"
  type          = "egress"
  to_port       = 65535
  from_port     = 1024
  protocol      = "tcp"
  sg_count      = "0"
  cidr_count    = "1"
  cidr_blocks   = [var.internet]
  sg_id         = aws_security_group.public-alb-sg.id
  description   = "ALB outbound"
}


# Inbound Rules for Lambda function security group on port 80 and 443 from ALB security group, Since it's repetitive using module
module "lambda_in" {
  source        = "./infrastructure/modules/security_group_rules"
  count         = length(var.ports)
  type          = "ingress"
  to_port       = var.ports[count.index]
  from_port     = var.ports[count.index]
  protocol      = "tcp"
  sg_count      = "1"
  cidr_count    = "0"
  source_sg_id  = aws_security_group.public-alb-sg.id
  sg_id         = aws_security_group.private-lambda-sg.id
  description   = "Lambda inbound"
}


# Fetch the vpc private endpoint prefix list (starts with pl-*) for dynamoDB
data "aws_prefix_list" "private_dynamoDB" {
  prefix_list_id = aws_vpc_endpoint.dynamoDB.prefix_list_id
}

# Outbound Rules for Lambda function security group on port 443 to dynamoDb endpoint when lambda will access DB
resource "aws_security_group_rule" "lambda_out_endpoint" {
  from_port                = 443
  protocol                 = "tcp"
  security_group_id        = aws_security_group.private-lambda-sg.id
  prefix_list_ids          = [data.aws_prefix_list.private_dynamoDB.prefix_list_id]
  to_port                  = 443
  type                     = "egress"
  description              = "Outbound Lambda EP"
}

# Logging for ALB in s3 bucket
resource "aws_s3_bucket" "alb_logs_s3" {
  bucket = "avi-app-alb-logs"
  acl = "private"
  server_side_encryption_configuration {
    rule {
      apply_server_side_encryption_by_default {
        sse_algorithm = "AES256"
      }
    }
  }
  force_destroy = true

  policy = jsonencode({
    Version   = "2012-10-17",
    Statement = [{
      Sid       = "PutALBLogs",
      Effect    = "Allow",
      Principal = "*"
      Action    = ["s3:PutObject"]
      Resource  = ["arn:aws:s3:::avi-app-alb-logs/logs/*"]}
    ]
  })
}

# Create ALB to balance and route the requests based on path --> Path based routing
resource "aws_lb" "lb" {
  name               = "avi-app-alb"
  load_balancer_type = "application"
  subnets            = aws_subnet.public_subnet.*.id
  security_groups    = [aws_security_group.public-alb-sg.id]
  internal           = false
  access_logs {
    bucket  = aws_s3_bucket.alb_logs_s3.bucket
    enabled = true
    prefix  = "logs/${local.path}"
  }
  lifecycle { create_before_destroy = true }
  tags = {
    Name = "avi-app-alb"
  }
  depends_on = [aws_security_group.public-alb-sg]
}

# IAM role for lambda (Do not format json policy below to align with indentation. TF does not like it
resource "aws_iam_role" "lambda_role" {
  name               = "avi-lambda-dynamoDBAccess"
  assume_role_policy = <<EOF
{"Version": "2012-10-17",
  "Statement": [{
    "Sid": "STSLambda",
    "Effect": "Allow",
    "Principal": {"Service": ["lambda.amazonaws.com"]},
    "Action": "sts:AssumeRole"
  }
]}
  EOF
}

# Create IAM role for Lambda
resource "aws_iam_policy" "lambda_policy" {
  name   = "lambdaPolicy"
  policy = file("infrastructure/policy/lambda_iam_policy.json")
}

# Attache the policy so that Lamnbda can access dynamoDB, CloudWatch logs etc, Read/Create/Update/Delete Network
# interfaces since it's inside a VPC
resource "aws_iam_policy_attachment" "attach_lambda_policy" {
  name       = "lambdaPolicyAttach"
  policy_arn = aws_iam_policy.lambda_policy.arn
  roles      = [aws_iam_role.lambda_role.name]
}

# Create Serverless API layer in form of Lambda
# zip lambda script. handling a single python file for POC purpose. In case of dependency management zip will be build
# as a prerequisite step and stored to artifacoty or any other binary management service. Download before running the terraform
data "archive_file" "py_api" {
  type        = "zip"
  source_file = "./application/${var.source_code}.py"
  output_path = "${var.source_code}.zip"
}


# Finally create Lambda function, Target group at ALB for specific endpoint (/app in this case), Attach lambda to that
# target group and attach target group to ALB listener. Also provide ALB permission to trigger lambda function
module "createLambda" {
  source          = "./infrastructure/modules/target"
  name            = var.lambda_name
  handler         = "${var.source_code}.lambda_handler"
  iam_role        = aws_iam_role.lambda_role.arn
  lambda_sgs      = [aws_security_group.private-lambda-sg.id]
  lambda_subnets  = aws_subnet.private_subnet.*.id
  db_table        = var.db_name
  alb_arn         = aws_lb.lb.arn
  vpc_id          = aws_vpc.app_vpc.id
  source_code     = data.archive_file.py_api.output_path
  depends_on      = [aws_dynamodb_table.app_db, aws_iam_role.lambda_role]
}

# Finally output the ALB DNS which will be used to connect to service. We can have
output "albDNS" {
  value = aws_lb.lb.dns_name
}


# Tech Debt:
# In case of region failure, Route53 to divert traffic to another region. It will need creation of a hosted zone, where
# you will create a record defining failover with Primary and Secondary ALB DNS created.