import os
import json
import boto3
import argparse
from pathlib import Path

# Capture the arguments being passed
arg_passed = argparse.ArgumentParser()
arg_passed.add_argument('-a', '--action', help='What terraform action to perform', required=True, default='plan',
                        choices={'plan', 'apply', 'destroy', 'planDestroy'})
arg_passed.add_argument('-e', '--env', help='Which environment deployment', required=True, default='poc',
                        choices={'poc'})


def run_cmd(cmd):
    """
    A method to run the os command inside python script
    :param cmd: what command you would like to run. In case of failure script will exit with an error
    """
    print('\n\nExecuting: {}\n\n'.format(cmd))
    status = os.system(cmd)
    if status != 0:
        raise Exception('Execution failed for: {}'.format(cmd))


# Create terraform state bucket to store the terraform files in advance
def create_bucket(client, bucket_name, aws_region):
    """
    Create bucket in your AWS account configured using AWS CLI
    :param client: boto3 s3
    :param bucket_name: Name of bucket needs to created
    :param aws_region: Region is be mentioned in client. s3 is global service yet reside in a region

    Capture the exception of bucket existence.
    """
    try:
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
        print('Encrypted State bucket created. {}'.format(bucket_name))
    except client.exceptions.BucketAlreadyExists:
        print('Bucket already exists, Continue.\n ######### \nIMPORTANT: If the bucket is not owned by you then '
              'Terraform will fail to execute. Either Let me know, I will delete the bucket or change the bucket name '
              'in application_structure.json.\n ######### \n')
    except Exception as e:
        if 'BucketAlreadyOwnedByYou' in str(e):
            print('Bucket exists and owned by you. {}'.format(bucket_name))


def main(tf_action, environment, config_file, aws_region=None):
    """
    Main method
    :param tf_action: Accepts the terraform action passed in
    :param environment: In which environment you want to deploy the infrastructure. You need to have different AWS
    account for different environment and make sure you update the application_structure.json based on endpoint config
    :param config_file: application_structure.json carrying the details about endpoint for respective environment
    :param aws_region: Specify the region if you need a specific one by default it eu-west-1
    :return:
    """
    aws_region = aws_region if aws_region else 'eu-west-1'
    home = str(Path.home())

    # Make sure AWS CLI has run and set up has been completed which generated below two files
    for setup_file in ['credentials', 'config']:
        file_name = os.path.join(home, '.aws', setup_file)
        if not os.path.exists(file_name):
            raise Exception('Required files are missing tp perform deployment from local. Make sure you have configured'
                            'you aws access and secrete key using AWS CLI which terraform will use to connect to AWS.')

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

    # Fetch required configurations from application_structure, like terraform state bucket, key. Application specific
    # details like endpoint (/app) and method (POST)
    state_bucket = app_struct['services']['state_bucket']
    state_key = app_struct['services']['state_key']
    endpoint = app_struct['services'][environment]['endpoint']
    methods = ','.join(app_struct['services'][environment]['method'])
    source_code = app_struct['services'][environment]['function']

    # Place in pre requisite to build the system. Check if state bucket exists if not create it
    s3_client = boto3.client('s3', region_name=aws_region)
    all_buckets = s3_client.list_buckets().get('Buckets')
    if not all_buckets:
        raise Exception('No bucket exists')

    state = False
    for bucket in all_buckets:
        if bucket.get('Name') == state_bucket:
            print('State bucket already there. {}'.format(state_bucket))
            state = True

    if not state:
        create_bucket(s3_client, state_bucket, aws_region)

    # We can have a separate tf state file for each endpoint deployment and this is the reason I wanted to separate the
    # standard network related stack from dynamic application infrastructure. Noted in Tech Debt
    tf_key = '{0}/{1}{2}-infra.tfstate'.format(environment, state_key, endpoint.replace('/', ''))
    required_vars = "-var 'endpoint={0}' -var 'methods={1}' -var 'source_code={2}'".format(endpoint, methods, source_code)
    run_cmd("terraform init -no-color -backend-config='bucket={0}' -backend-config='key={1}'".format(state_bucket, tf_key))
    run_cmd('terraform get --update')
    if tf_action == 'plan':
        run_cmd('terraform {0} -no-color {1}'.format(tf_action, required_vars))
        return
    elif tf_action == 'planDestroy':
        run_cmd('terraform plan -no-color -destroy {0}'.format(required_vars))
        return
    else:
        run_cmd('terraform {0} -no-color -auto-approve {1}'.format(tf_action, required_vars))
        return


if __name__ == '__main__':
    args = vars(arg_passed.parse_args())

    # Which terraform action you want to perform plan, apply, destroy, plan for destroy (planDestroy)
    action = args['action']

    # Below options are to provide the flexibility of choosing the parameter based on environment, It can be made more
    # flexible by passing endpoint itself. Like which endpoint you want to deploy and accordingly decide the deployment
    # variables
    env = args['env']
    # A static file defining the structure/parameters/config of application
    application_structure = 'application_structure.json'
    main(action, env, application_structure)
