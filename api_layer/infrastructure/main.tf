variable db_name             {default = "avi-app-dynamo"}
variable lambda_name         {default = "avi-lambda-app-api"}
variable endpoint            {}
variable source_code         {}
variable methods             {}
variable tf_region           {}

# Required terraform version and AWS region
terraform {
  required_version = ">=0.12"
  backend "s3" {}
}


# Required terraform provider, AWS in this case deploying the solution to AWS region eu-west-1
provider "aws" {
  region = var.tf_region
}

# IAM role for lambda (Do not format json policy below to align with indentation. TF does not like it
resource "aws_iam_role" "lambda_role" {
  name               = "avi-lambda-${var.tf_region}-dynamoDBAccess"
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
  name   = "lambdaPolicy-${var.tf_region}"
  policy = file("./policy/lambda_iam_policy.json")
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
  source_file = "../${var.source_code}.py"
  output_path = "${var.source_code}.zip"
}


# Finally create Lambda function, Target group at ALB for specific endpoint (/app in this case), Attach lambda to that
# target group and attach target group to ALB listener. Also provide ALB permission to trigger lambda function
module "createLambda" {
  source          = "./modules/target"
  name            = var.lambda_name
  handler         = "${var.source_code}.lambda_handler"
  iam_role        = aws_iam_role.lambda_role.arn
  db_table        = var.db_name
  source_code     = data.archive_file.py_api.output_path
  depends_on      = [aws_iam_role.lambda_role]
  endpoint        = var.endpoint
  methods         = var.methods
  tf_region       = var.tf_region
}