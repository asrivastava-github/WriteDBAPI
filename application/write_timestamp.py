# lambda_func.py
# import the required modules

import os
import boto3
import json
from datetime import datetime


def prepare_response(code, body=None):
  body = body if body else ''
  msg = 'OK' if str(code).startswith('2') else 'NOT OK'

  return {
    "statusCode": code,
    "statusDescription": "{0} {1}".format(code, msg),
    "isBase64Encoded": False,
    "body": body,
    "headers": {
      "Content-Type": "text/html; charset=utf-8"
    }
  }


# endpoint = os.environ['PATH']
# accept_methods = os.environ['METHODS'].replace(' ', '').replace('"', '').replace("'", "").split(',')

# few standard error
not_found_error = json.dumps({'error': 'Requested Resource is not found. No timestamp has been recorded yet.'}), 404
bad_request_error = json.dumps({'error': 'Bad Request, Server is unable to understand the request. '
                                         'No timestamp has been recorded yet.'}), 400
std_error = json.dumps({'error': 'This logic has not been code. Implementation pending.'}), 501
server_error = """'error': 'Unable to put item in DB: {}'"""
happy_response = prepare_response(200)

welcome_resp = happy_response.copy()
welcome_resp['body'] = """<html><head><title>writeDB</title><style>html, body {margin: 0; padding: 0;font-family: arial; 
font-weight: 700; font-size: 3em; text-align: center;}</style></head><body><p>Welcome to HomePage</p></body></html>"""

# Fetch the Table name from environment variable. It can be passed via terraform as well
DB_TABLE = os.environ['DB_TABLE']
# Create boto3 client to perform the dynamoDB actions
client = boto3.client('dynamodb')
# String format of time
str_time_format = '%Y-%m-%d %H:%M:%S.%f'


def fetch_entry(unique_id):
  '''
  A function to fetch the dynamodb content of a specific key
  :param unique_id: Unique key of dynamo DB
  :return: The entry of table for the key
  '''
  entry_exists = False
  item = None
  try:
    resp = client.get_item(
      TableName=DB_TABLE,
      Key={'uniqueId': {'S': unique_id}}
    )
    item = resp.get('Item')
    if item:
      entry_exists = True
  except Exception as e:
    print('Unique Item does not exists: {}'.format(unique_id))

  return entry_exists, item


# fetch the existing date in case of testing
def get_time_stamp(unique_id):
  entry, item = fetch_entry(unique_id)
  if not entry:
    return not_found_error

  return json.dumps({
    'uniqueId': item.get('S').get('uniqueId'),
    'timeStamp': item.get('S').get('timeStamp'),
    'clientIP': item.get('S').get('clientIP'),
    'protocol': item.get('S').get('protocol')
  })


def lambda_handler(event, context):
  print(event)
  '''
  Main Lambda handler function
  :param event: Event received by Application Load balancer
  :param context: Context received by Application Load balancer
  :return:
  '''
  if not event:
    return std_error

  # Fetch required request details
  request_method = event.get('httpMethod')
  request_path = event.get('path')
  headers = event.get('headers')
  if request_path == '/health':
    if 'user-agent' in headers:
      if headers['user-agent'] == 'ELB-HealthChecker/2.0':
        return happy_response
  else:
    trace_id = headers.get('x-amzn-trace-id')
    client_ip = headers.get('x-forwarded-for')
    serve_port = headers.get('x-forwarded-port')
    protocol = headers.get('x-forwarded-proto')
    print('{0}\n{1}\n{2}\n{3}\n{4}\n{5}'.format(trace_id, client_ip, serve_port, protocol, request_path, request_method))

    timestamp = datetime.strftime(datetime.now(), str_time_format)
    # To make key unique, adding timestamp along with trace id. AWS claims it to be unique but not sure how it will be
    # over the period of time. We can have a fancy hash generator but keeping it simple.
    unique_id = '{0}{1}'.format(trace_id, timestamp.replace(' ', ''))

    if not (trace_id and client_ip and serve_port and protocol):
      return bad_request_error
    if request_path == '/' and request_method == 'GET':
      return welcome_resp
    if request_path == '/app' and request_method == 'POST':
      # Making Lambda idempotent
      entry, item = fetch_entry(unique_id)
      if entry and item:
        return {'info': 'DB timestamp entry already exists with uniqueID: {}.'.format(unique_id)}, 200
      else:
        try:
          print('Writing timestamp to DynamoDB, uniqueID: {}'.format(unique_id))
          client.put_item(
            TableName=DB_TABLE,
            Item={
              'uniqueId': {'S': unique_id},
              'timeStamp': {'S': timestamp},
              'clientIP': {'S': client_ip},
              'protocol': {'S': protocol},
            }
          )
        except Exception as e:
          return json.dumps(server_error.format(e)), 500

      entry, item = fetch_entry(unique_id)
      if not entry:
        return not_found_error
      return json.dumps(item), 201

    if request_path == '/app' and request_method == 'GET':
      entry, item = fetch_entry(unique_id)
      if not entry:
        return not_found_error
      return json.dumps(item), 201


  # from flask import Flask, request
  # from flask_restful import Resource, Api
  # import sys
  # import os
  #
  # app = Flask(__name__)
  # api = Api(app)
  # port = 5100
  #
  # if sys.argv.__len__() > 1:
  #   port = sys.argv[1]
  # print("Api running on port : {} ".format(port))
  #
  # class topic_tags(Resource):
  #   def get(self):
  #     return {'hello': 'world world'}
  #
  # api.add_resource(topic_tags, '/')
  #
  # if __name__ == '__main__':
  #   app.run(host="0.0.0.0", port=port)