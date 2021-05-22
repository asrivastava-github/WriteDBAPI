# write_timestamp.py
# import the required modules

import os
import boto3
from datetime import datetime
from flask import Flask, jsonify, request
app = Flask(__name__)

# Fetch the Table name from environment variable. It can be passed via terraform as well
USERS_TABLE = os.environ['TIME_TABLE']
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
    resp = client.get_item(
        TableName=USERS_TABLE,
        Key={'uniqueId': unique_id }
    )
    item = resp.get('Item')
    if item:
        entry_exists = True

    return entry_exists, item



# flask standard of defining the routes/endpoints. homepage
@app.route('/')
def home():
    return 'Welcome to homepage of App which provides endpoint (/app) to write timestamp to Database.' \
           '(DynamoDB in this case)'


# flask standard of defining the routes/endpoints. fetch the existing date in case of testing
@app.route('/appdata')
def get_time_stamp(unique_id):
    entry, item = fetch_entry(unique_id)
    if not entry:
        return jsonify({'error': 'No timestamp has been recorded yet.'}), 404

    return jsonify({
        'uniqueId': item.get('uniqueId'),
        'timeStamp': item.get('timeStamp')
    })


# flask standard of defining the routes/endpoints. Endpoint as per requirement to receive request from client
@app.route('/app', methods=['POST'])
def write_time_stamp(timestamp):
    trace_id = request.json.get('X-Amzn-Trace-Id')

    # To make key unique adding timestamp along with trace id. AWS claims it to be unique but not sure how it will be
    # over the period of time. We can have a fancy hash generator but keeping it simple.
    unique_id = '{0}{1}'.format(trace_id, timestamp.replace(' ', ''))

    # Making Lambda idempotent
    entry, item = fetch_entry(unique_id)
    if entry:
        print('Entry already exists.')
    else:
        client.put_item(
            TableName=USERS_TABLE,
            Item={
                'uniqueId': unique_id,
                'timeStamp': timestamp
            }
        )

    entry, item = fetch_entry(unique_id)
    if entry:
        return jsonify(item)
    else:
        return jsonify({'error': 'No timestamp has been recorded yet.'}), 404
