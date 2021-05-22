account_id         = ""
state_bucket       = "avi-assignment-api-service"
state_key          = "avi-assignment-api-service-state.tfstate"
cidr_block         = "11.0.0.0/24"
subnet_cidr_block1 = "11.0.0.0/28"
subnet_cidr_block2 = "11.0.0.16/28"
lb_log_bucket      = "avi-lb-logs"
region             = "eu-west-1"
tf_version         = ">=0.12.0"
db_name            = "avi-app-db"
lambda_name        = "avi-lambda-api"
dynamo_read        = 20
dynamo_write       = 20
aws_provider       = ">=3.38"