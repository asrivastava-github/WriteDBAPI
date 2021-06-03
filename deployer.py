import os
import json
import boto3
import argparse
import logging
logging.basicConfig(level=logging.INFO)

# Capture the arguments being passed
arg_passed = argparse.ArgumentParser()
arg_passed.add_argument('-a', '--action', help='What terraform action to perform', required=True, default='plan',
                        choices={'plan', 'apply', 'destroy', 'planDestroy', 'load_test'})
arg_passed.add_argument('-e', '--env', help='Which environment deployment', required=True, default='poc',
                        choices={'poc'})
arg_passed.add_argument('-s', '--stack', help='Which stack to deploy', required=True, default='network_layer',
                        choices={'network_layer', 'api_layer'})


def run_cmd(cmd, logger):
    """
    A method to run the os command inside python script
    :param cmd: what command you would like to run. In case of failure script will exit with an error
    :param logger:
    """
    logger.info('\n\nExecuting: {}\n\n'.format(cmd))
    status = os.system(cmd)
    if status != 0:
        raise Exception('Execution failed for: {}'.format(cmd))


# Create terraform state bucket to store the terraform files in advance
def create_bucket(client, bucket_name, aws_region, logger):
    """
    Create bucket in your AWS account configured using AWS CLI
    :param client: boto3 s3
    :param bucket_name: Name of bucket needs to created
    :param aws_region: Region is be mentioned in client. s3 is global service yet reside in a region
    :param logger

    Capture the exception of bucket existence.
    """
    try:
        logger.info('Creating bucket: {}'.format(bucket_name))
        client.create_bucket(
            ACL='private',
            Bucket=bucket_name,
            CreateBucketConfiguration={'LocationConstraint': aws_region}
        )
        client.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                'BlockPublicAcls': True,
                'IgnorePublicAcls': True,
                'BlockPublicPolicy': True,
                'RestrictPublicBuckets': False
            }
        )
        client.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={'Rules': [{'ApplyServerSideEncryptionByDefault': {'SSEAlgorithm': 'AES256'}}]}
        )
        logger.info('Encrypted State bucket created. {}'.format(bucket_name))
    except client.exceptions.BucketAlreadyExists:
        logger.info('Bucket already exists, Continue.\n ######### \nIMPORTANT: If the bucket is not owned by you then '
                    'Terraform will fail to execute. Either Let me know, I will delete the bucket or change the bucket name '
                    'in application_structure.json.\n ######### \n')
    except Exception as e:
        if 'BucketAlreadyOwnedByYou' in str(e):
            logger.info('Bucket exists and owned by you. {}'.format(bucket_name))


def main(tf_action, environment, config_file, stack, logger):
    """
    Main method
    :param tf_action: Accepts the terraform action passed in
    :param environment: In which environment you want to deploy the infrastructure. You need to have different AWS
    account for different environment and make sure you update the application_structure.json based on endpoint config
    :param config_file: application_structure.json carrying the details about endpoint for respective environment
    :param stack
    :param logger
    :return:
    """

    tf_plan_bin = 'plan.out'
    # Check If application_structure file exists, It's just a way to make the deployment easy and control
    # via environment or any meaningful key.
    if not os.path.exists(config_file):
        raise Exception('File which defines the application structure is missing. {}'.format(config_file))

    # If file exists get the value in a map as it's json file
    with open(config_file) as f_r:
        app_struct = json.load(f_r)

    # Else exit the deployment
    if not app_struct:
        raise Exception('Application Structure definition missing: {}'.format(config_file))

    region = app_struct['services'].get('aws_region')
    aws_region = region if region else 'eu-west-1'

    # Fetch required configurations from application_structure, like terraform state bucket, key. Application specific
    # details like endpoint (/app) and method (POST)
    state_bucket = app_struct['services']['state_bucket'].format(aws_region)
    state_key = app_struct['services']['state_key']

    # Place in pre requisite to build the system. Check if state bucket exists if not create it
    s3_client = boto3.client('s3', region_name=aws_region)
    all_buckets = s3_client.list_buckets().get('Buckets')
    if not all_buckets:
        raise Exception('No bucket exists')

    state = False
    for bucket in all_buckets:
        if bucket.get('Name') == state_bucket:
            logger.info('State bucket already there. {}'.format(state_bucket))
            state = True

    if not state:
        create_bucket(s3_client, state_bucket, aws_region, logger)

    # We can have a separate tf state file for each endpoint deployment and this is the reason I wanted to separate the
    # standard network related stack from dynamic application infrastructure.
    if stack == 'network_layer':
        logger.info('Deploying Standard Network Layer which will include VPC, Subnet, IGW, Route tables, NACLs, ALB, SGs etc.')
        tf_key = '{0}/{1}-network-layer.tfstate'.format(environment, state_key)
        required_vars = "-var 'tf_region={0}'".format(aws_region)
        run_cmd("cd network_layer && terraform init -no-color -backend-config='bucket={0}' -backend-config='key={1}' -backend-config 'region={2}'".format(state_bucket, tf_key, aws_region), logger)
        run_cmd('cd network_layer && terraform get --update', logger)

        if action in ['destroy', 'planDestroy']:
            run_cmd('cd network_layer && terraform plan -no-color -destroy {0}'.format(required_vars), logger)
        else:
            run_cmd('cd network_layer && terraform plan -no-color {1} -out {2}'.format(tf_action, required_vars, tf_plan_bin), logger)

        if tf_action == 'apply':
            run_cmd('cd network_layer && terraform {0} -no-color -auto-approve {1}'.format(tf_action, tf_plan_bin), logger)
        elif tf_action == 'destroy':
            run_cmd('cd network_layer && terraform {0} -no-color -auto-approve {1}'.format(tf_action, required_vars), logger)

    if stack == 'api_layer':
        for api in app_struct['services'][environment]:
            endpoint = api['endpoint']
            methods = ','.join(api['methods'])
            source_code = api['function']
            logger.info('Deploying {} API Layer which will include Lambda, ALB target groups etc.'.format(endpoint))
            tf_key = '{0}/{1}{2}-api-layer.tfstate'.format(environment, state_key, endpoint.replace('/', ''))
            required_vars = "-var 'endpoint={0}' -var 'methods={1}' -var 'source_code={2}' -var 'tf_region={3}'".format(endpoint, methods, source_code, aws_region)
            run_cmd("cd api_layer/infrastructure && terraform init -no-color -backend-config='bucket={0}' -backend-config='key={1}' -backend-config 'region={2}'".format(state_bucket, tf_key, aws_region), logger)
            run_cmd('cd api_layer/infrastructure && terraform get --update', logger)

            if action in ['destroy', 'planDestroy']:
                run_cmd('cd api_layer/infrastructure && terraform plan -no-color -destroy {0}'.format(required_vars), logger)
            else:
                run_cmd('cd api_layer/infrastructure && terraform plan -no-color {1} -out {2}'.format(tf_action, required_vars, tf_plan_bin), logger)

            if tf_action == 'apply':
                run_cmd('cd api_layer/infrastructure && terraform {0} -no-color -auto-approve {1}'.format(tf_action, tf_plan_bin), logger)
            elif tf_action == 'destroy':
                run_cmd('cd api_layer/infrastructure && terraform {0} -no-color -auto-approve {1}'.format(tf_action, required_vars), logger)

            if tf_action == 'load_test':
                tf_key = '{0}/{1}-network-layer.tfstate'.format(environment, state_key)
                run_cmd("cd network_layer && terraform init -no-color -backend-config='bucket={0}' -backend-config='key={1}' -backend-config 'region={2}'".format(state_bucket, tf_key, aws_region), logger)
                run_cmd('cd network_layer && terraform get --update', logger)
                curr_path = os.path.dirname(os.path.realpath(__file__))
                alb_dns_file = os.path.join(curr_path, 'alb_dns')
                run_cmd('cd network_layer && terraform output', logger)
                run_cmd('cd network_layer && terraform output > {}'.format(alb_dns_file), logger)
                with open(alb_dns_file) as f:
                    lines = f.readlines()
                for line in lines:
                    if 'albDNS = ' in line:
                        endpoint = line.replace('albDNS = ', '').replace('"', '').strip()
                logger.info(endpoint)
                run_cmd('cd {0} && locust -f locustfile.py --host=http://{1} --run-time=20s --headless -u 10 -r 10'.format(stack, endpoint), logger)



if __name__ == '__main__':
    args = vars(arg_passed.parse_args())

    # Which terraform action you want to perform plan, apply, destroy, plan for destroy (planDestroy)
    action = args['action']

    # Below options are to provide the flexibility of choosing the parameter based on environment, It can be made more
    # flexible by passing endpoint itself. Like which endpoint you want to deploy and accordingly decide the deployment
    # variables
    env = args['env']
    # A static file defining the structure/parameters/config of application

    # Which stack is being deployed first
    tf_stack = args['stack']
    application_structure = 'application_structure.json'
    app_logger = logging.getLogger(action)
    main(action, env, application_structure, tf_stack, app_logger)
