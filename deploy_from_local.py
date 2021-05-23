import os
import json
import boto3
import argparse
from pathlib import Path
from zipfile import ZipFile

arg_passed = argparse.ArgumentParser()
arg_passed.add_argument('-a', '--action', help='What terraform action to perform', required=True, default='plan',
                        choices={'plan', 'apply', 'destroy', 'planDestroy'})
arg_passed.add_argument('-e', '--env', help='Which environment deployment', required=True, default='prod',
                        choices={'prod'})
arg_passed.add_argument('-p', '--path', help='which endpoint to deploy, defined in config', required=True, default='/app',
                        choices={'/app'})


def zip_app_files(app_path):
    # initializing empty file paths list
    file_paths = list()
    # crawling through directory and subdirectories"aws_security_group" "private-lambda-sg" {
    for root, directories, files in os.walk(app_path):
        for filename in files:
            # join the two strings in order to form the full filepath.
            filepath = os.path.join(root, filename)
            file_paths.append(filepath)

    # returning all file paths
    if not file_paths:
        raise Exception('Application code directory not found.')

    # writing files to a zipfile
    with ZipFile('{}.zip'.format(app_path, 'w')) as zip:
        # writing each file one by one
        for file in file_paths:
            zip.write(file)

    print('Lambda code has been zipped successfully!')


def run_cmd(cmd):
    print('\n\nExecuting: {}\n\n'.format(cmd))
    status = os.system(cmd)
    if status != 0:
        raise Exception('Execution failed for: {}'.format(cmd))


def create_infra(tf_bucket, tf_key, tf_action, required_vars):
    run_cmd("terraform init -no-color -backend-config='bucket={0}' -backend-config='key={1}'".format(tf_bucket, tf_key))
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

# Create bucket in advance
def create_bucket(client, bucket_name, aws_region, num=1):
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
        num += 1
        bucket_name = '{0}-{1}'.format(bucket_name, num)
        create_bucket(client, bucket_name, num)
    except Exception as e:
        if 'BucketAlreadyOwnedByYou' in str(e):
            print('Bucket ')

def main(tf_action, environment, svc_path, config_file, aws_region=None, infra=None):
    aws_region = aws_region if aws_region else 'eu-west-1'
    home = str(Path.home())
    for setup_file in ['credentials', 'config']:
        file_name = os.path.join(home, '.aws', setup_file)
        if not os.path.exists(file_name):
            raise Exception('Required files are missing tp perform deployment from local. Make sure you have configured'
                            'you aws access and secrete key using AWS CLI which terraform will use to connect to AWS.')

    if not os.path.exists(config_file):
        raise Exception('File which defines the application structure is missing. {}'.format(config_file))
    with open(config_file) as f_r:
        app_struct = json.load(f_r)

    if not app_struct:
        raise Exception('Application Structure definition missing: {}'.format(config_file))

    if not svc_path in app_struct['services'][environment]:
        raise Exception('Service endpoint ({}) details is missing in Application Structure definition.'.format(svc_path))

    # Fetch required configurations
    state_bucket = app_struct['services']['state_bucket']
    state_key = app_struct['services']['state_key']
    methods = ','.join(app_struct['services'][environment][svc_path]['method'])
    source_code = app_struct['services'][environment][svc_path]['function']
    tf_var_fl = os.path.join('infrastructure', 'variables', environment, '{}.tfvars'.format(source_code))

    # Place in pre requisite
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

    if infra == 'network':
        tf_key = '{0}/{1}{2}-infra.tfstate'.format(environment, state_key, svc_path.replace('/', ''))
        required_vars = "-var 'endpoint={0}' -var 'methods={1}' -var 'source_code={2}' -var-file={3}"\
            .format(svc_path, methods, source_code, tf_var_fl)
        create_infra(state_bucket, tf_key, tf_action, required_vars)

    tf_key = '{0}/{1}{2}-infra.tfstate'.format(environment, state_key, svc_path.replace('/', ''))
    required_vars = "-var 'endpoint={0}' -var 'methods={1}' -var 'source_code={2}'".format(svc_path, methods,
                                                                                           source_code)
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
    action = args['action']
    env = args['env']
    endpoint = args['path']
    app_struct = 'application_structure.json'
    main(action, env, endpoint, app_struct)


