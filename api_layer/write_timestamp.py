# lambda_func.py
# import the required modules

import os
import boto3
from datetime import datetime
from botocore.config import Config

# A standard welcome message on homepage of ALB DNS
std_welcome = """<html><head><title>writeDB</title><style>html, body {margin: 0; padding: 0;font-family: arial; 
font-weight: 700; font-size: 3em; text-align: center;}</style></head><body><p>Welcome to HomePage</p></body></html>"""


def prepare_response(code, result=None, resp_type=None):
    """
    A method to send the response back to ALB, post processing
    :param code: What status code you need to send as response
    :param result: What would be body of response
    :param resp_type: Whether you want to send text/html or application/json
    :return: the response
    """
    body = result if result else std_welcome
    msg = 'OK' if str(code).startswith('2') else 'NOT OK'
    resp_type = resp_type if resp_type else 'application/json'

    return {
        'statusCode': code,
        'statusDescription': '{0} {1}'.format(code, msg),
        'isBase64Encoded': False,
        'body': '{}\n'.format(body),
        'headers': {
            'Content-Type': '{}; charset=utf-8'.format(resp_type)
        }
    }


# few standard error
not_found_error = prepare_response(404, {'error': 'Requested Resource is not found. No timestamp is recorded yet.'})
bad_request_error = prepare_response(400, {'error': 'Bad Request, Server is unable to understand the request. No '
                                                    'timestamp has been recorded yet.'}, resp_type='application/json')
std_error = prepare_response(501, {'error': 'This logic has not been code. Implementation pending.'})

# Fetch the Table name from environment variable. It can be passed via terraform as well
DB_TABLE = os.environ['DB_TABLE']

aws_region = os.environ['REGION']
# You can define config specific to your requirement inside boto3 client
_config = Config(region_name=aws_region, signature_version='v4', retries={'max_attempts': 5, 'mode': 'standard'})

# Create boto3 resource to perform the dynamoDB actions
dd_resource = boto3.resource('dynamodb', region_name=aws_region, config=_config,
                             endpoint_url='https://dynamodb.{}.amazonaws.com'.format(aws_region))
# Get connection to the table created
TIME_TABLE = dd_resource.Table(DB_TABLE)
# String format of time
str_time_format = '%Y-%m-%d %H:%M:%S.%f'


def fetch_entry(unique_id, time_stamp):
    """
    A function to fetch the dynamodb content of a specific key
    :param unique_id: Unique key of dynamo DB
    :param time_stamp: Time stamp key
    :return: The entry of table for the key
    """
    print('Fetching items with unique_id: {}'.format(unique_id))
    entry_exists = False
    item = None
    try:
        resp = TIME_TABLE.get_item(Key={'uniqueId': unique_id, 'timeStamp': time_stamp})
        print(resp)
        item = resp.get('Item')
        print(item)
        if item:
            entry_exists = True
    except Exception as e:
        print('Unique Item does not exists: {0}. Error: {1}'.format(unique_id, e))

    return entry_exists, item


def fetch_all_keys():
    """
    Scan and return all the records stored in dynamoDB, It is just for POC in reality these kind of high IO operation
    are not recommended. Restrict it to max number of results returned using "TotalSegments" or provide filter keys
    "ScanFilter", "ExclusiveStartKey" etc
    :return:
    """
    response = TIME_TABLE.scan()
    items = response['Items']
    items.sort(key=lambda x: x['timeStamp'])
    response = ''
    for item in items:
        response = '{0}\n{1}'.format(response, item)
    return response


def lambda_handler(event, context):
    print(event)
    """
    Main Lambda handler function
    :param event: Event json received by Application Load balancer
    :param context: Context method received by Application Load balancer
    :return:
    """
    if not event:
        return std_error

    # Fetch required request details
    request_method = event.get('httpMethod')
    request_path = event.get('path')
    headers = event.get('headers')

    # If it's for health check response to ALB with 200
    if request_path == '/health':
        if 'user-agent' in headers:
            if headers['user-agent'] == 'ELB-HealthChecker/2.0':
                return prepare_response(200, resp_type='text/html')
    else:
        # Otherwise fetch the further details from header
        trace_id = headers.get('x-amzn-trace-id')
        client_ip = headers.get('x-forwarded-for')
        serve_port = headers.get('x-forwarded-port')
        protocol = headers.get('x-forwarded-proto')
        # Just for logging purpose in POC, print the captured values
        print('{0}\n{1}\n{2}\n{3}\n{4}\n{5}'.format(trace_id, client_ip, serve_port, protocol, request_path,
                                                    request_method))

        # Generate the stamp to be put inside dynamoDB
        timestamp = datetime.strftime(datetime.now(), str_time_format)
        # To make hash_key key unique, adding timestamp along with trace id. AWS claims trace id it to be unique but not
        # sure how long it will be over the period of time. We can have a fancy hash generator but keeping it simple.
        unique_id = '{0}{1}'.format(trace_id, timestamp.replace(' ', ''))

        # If the required value to be placed in are not present, return bad request response
        if not (trace_id and client_ip and serve_port and protocol):
            return bad_request_error

        # Respond to a home page
        if request_path == '/' and request_method == 'GET':
            return prepare_response(200, resp_type='text/html')

        # Handle actual requirement
        if request_path == '/app' and request_method == 'POST':
            # Making Lambda idempotent to be on safer side. In case multiple instance of lambda gets trigger check the
            # existence of unique first, However I have not observed this to be happening with ALB + Lambda
            entry, item = fetch_entry(unique_id, timestamp)
            if entry and item:
                return prepare_response(200, {'info': 'DB timestamp entry already exists with uniqueID: {}.'
                                        .format(unique_id)})
            else:
                # Try writing timestamp to DB
                try:
                    print('Writing timestamp to DynamoDB, uniqueID: {}'.format(unique_id))
                    TIME_TABLE.put_item(
                        Item={
                            'uniqueId': unique_id,
                            'timeStamp': timestamp,
                            'clientIP': client_ip,
                            'protocol': protocol,
                        }
                    )
                except Exception as e:
                    # Send error message as server error in case of issue.
                    return prepare_response(500, e)

            # post successful write fetch the item
            entry, item = fetch_entry(unique_id, timestamp)

            # if not item is fetched return the not found error
            if not entry:
                return not_found_error

            # Finally send the timestamp written to DB as response
            return prepare_response(201, item['timeStamp'])


        # Just an add on in case /app is hit on browser just show all the entries inside the DB
        if request_path == '/app' and request_method == 'GET':
            recent_possible_items = fetch_all_keys()
            if not recent_possible_items:
                return not_found_error
            return prepare_response(200, recent_possible_items)
