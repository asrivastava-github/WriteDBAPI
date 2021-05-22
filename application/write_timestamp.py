# lambda_func.py
# import the required modules

import os
import boto3
import json
from datetime import datetime


endpoint = os.environ['PATH']
accept_methods = os.environ['METHODS'].replace(' ', '').replace('"', '').replace("'", "").split(',')

# few standard error
not_found_error = json.dumps({'error': 'No timestamp has been recorded yet.'}), 404
bad_request_error = json.dumps({'error': 'No timestamp has been recorded yet.'}), 400

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
  resp = client.get_item(
    TableName=DB_TABLE,
    Key={'uniqueId': {'S': unique_id}}
  )
  item = resp.get('Item')
  if item:
    entry_exists = True

  return entry_exists, item


# fetch the existing date in case of testing
def get_time_stamp(unique_id):
  entry, item = fetch_entry(unique_id)
  if not entry:
    return not_found_error

  return json.dumps({
    'uniqueId': item.get('S').get('uniqueId'),
    'timeStamp': item.get('S').get('timeStamp')
  })


def lambda_handler(event, context):
  '''
  Main Lambda handler function
  :param event: Event received by Application Load balancer
  :param context: Context received by Application Load balancer
  :return:
  '''

  # Default routing Error page

  response = {
    "statusCode": 200,
    "statusDescription": "200 OK",
    "isBase64Encoded": False,
    "headers": {
      "Content-Type": "text/html; charset=utf-8"
    }
  }

  response['body'] = """<html>
  <head>
  <title>Hello World!</title>
  <style>
  html, body {
  margin: 0; padding: 0;
  font-family: arial; font-weight: 700; font-size: 3em;
  text-align: center;
  }
  </style>
  </head>
  <body>
  <p>Hello World!</p>
  </body>
  </html>"""
  return response

  request_method = event['httpMethod']
  request_path = event['path']
  trace_id = event['headers']['x-amzn-trace-id']
  if not(request_method and request_path and trace_id):
    return bad_request_error

  if request_method in accept_methods and request_path == endpoint:
    timestamp = datetime.strftime(datetime.now(), str_time_format)

    # To make key unique, adding timestamp along with trace id. AWS claims it to be unique but not sure how it will be
    # over the period of time. We can have a fancy hash generator but keeping it simple.
    unique_id = '{0}{1}'.format(trace_id, timestamp.replace(' ', ''))

    # Making Lambda idempotent
    entry, item = fetch_entry(unique_id)
    if entry:
      print('Entry already exists.')
    else:
      client.put_item(
        TableName=DB_TABLE,
        Item={
          'uniqueId': {'S': unique_id},
          'timeStamp': {'S': timestamp}
        }
      )

    entry, item = fetch_entry(unique_id)
    if not entry:
      return not_found_error
    return json.dumps(item)

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

  dict = {'requestContext': {'elb': {
    'targetGroupArn': 'arn:aws:elasticloadbalancing:eu-west-1:377219046518:targetgroup/avi-app-tg/498640211513e2a6'}},
   'httpMethod': 'GET', 'path': '/favicon.ico', 'queryStringParameters': {},
   'headers': {'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
               'accept-encoding': 'gzip, deflate', 'accept-language': 'en-US,en;q=0.9', 'connection': 'keep-alive',
               'host': 'avi-app-alb-299236829.eu-west-1.elb.amazonaws.com',
               'referer': 'http://avi-app-alb-299236829.eu-west-1.elb.amazonaws.com/app',
               'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36',
               'x-amzn-trace-id': 'Root=1-60a83035-6d821077125160997936d9f7', 'x-forwarded-for': '81.140.213.55',
               'x-forwarded-port': '80', 'x-forwarded-proto': 'http'}, 'body': '', 'isBase64Encoded': False}
  dict2 = {'requestContext': {'elb': {'targetGroupArn': 'arn:aws:elasticloadbalancing:eu-west-1:377219046518:targetgroup/avi-app-tg/498640211513e2a6'}}, 'httpMethod': 'GET', 'path': '/app', 'queryStringParameters': {}, 'headers': {'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9', 'accept-encoding': 'gzip, deflate', 'accept-language': 'en-US,en;q=0.9', 'cache-control': 'max-age=0', 'connection': 'keep-alive', 'host': 'avi-app-alb-299236829.eu-west-1.elb.amazonaws.com', 'upgrade-insecure-requests': '1', 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36', 'x-amzn-trace-id': 'Root=1-60a83035-7309235e4567016e64e6e950', 'x-forwarded-for': '81.140.213.55', 'x-forwarded-port': '80', 'x-forwarded-proto': 'http'}, 'body': '', 'isBase64Encoded': False}


  dict3 = {'requestContext': {'elb': {'targetGroupArn': 'arn:aws:elasticloadbalancing:eu-west-1:377219046518:targetgroup/avi-app-tg/498640211513e2a6'}}, 'httpMethod': 'GET', 'path': '/favicon.ico', 'queryStringParameters': {}, 'headers': {'accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8', 'accept-encoding': 'gzip, deflate', 'accept-language': 'en-US,en;q=0.9', 'connection': 'keep-alive', 'host': 'avi-app-alb-299236829.eu-west-1.elb.amazonaws.com', 'referer': 'http://avi-app-alb-299236829.eu-west-1.elb.amazonaws.com/app', 'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36', 'x-amzn-trace-id': 'Root=1-60a83032-469449f240ea30471729855d', 'x-forwarded-for': '81.140.213.55', 'x-forwarded-port': '80', 'x-forwarded-proto': 'http'}, 'body': '', 'isBase64Encoded': False}


