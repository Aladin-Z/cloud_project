#!/usr/bin/python
import json
import random

import pymysql.cursors
from flask import Flask, request, Response
from pythonping import ping
from sshtunnel import SSHTunnelForwarder

# master and slaves configurations
MASTER_CONFIG = {
    "ip": "44.201.120.181",
    "port": 3306,
    "name": "MASTER"
}

SLAVE_CONFIGS = [
    {"ip": "54.211.6.184",    "port": 5001,   "name": "SLAVE_1"},
    {"ip": "44.212.70.94",    "port": 5002,   "name": "SLAVE_2"},
    {"ip": "54.158.97.142",    "port": 5003,   "name": "SLAVE_3"},
]

def make_response(route_type, ip, server_name, query_response):
    json_response = json.dumps({
        "source": server_name,
        "responseBody": str(query_response)
    })
    return Response(json_response, mimetype='application/json')


# setup sshtunnels
servers = []
for idx, slave_config in enumerate(SLAVE_CONFIGS):
    print(
        f"Starting forwarding for {slave_config['ip']} -> 127.0.0.1:{slave_config['port']}")
    server = SSHTunnelForwarder(
        (slave_config["ip"], 22),
        ssh_pkey="/home/ubuntu/private_key.pem",
        ssh_username="ubuntu",
        local_bind_address=('127.0.0.1', slave_config["port"]),
        allow_agent=False,
        remote_bind_address=(MASTER_CONFIG["ip"], MASTER_CONFIG["port"]))
    server.start()
    servers.append(server)


# simple function that pings a host and returns the average
def ping_instance(host):
    ping_result = ping(target=host, count=5, timeout=2)
    avg_ping = ping_result.rtt_avg_ms
    print(f"{host} ping : {avg_ping}ms")
    return avg_ping


# flask Application : defines our endpoints and their logic
app = Flask(__name__)


@app.route('/normal')
def normal_endpoint():
    # forward the request directly to the master
    connection = pymysql.connect(host=MASTER_CONFIG["ip"],
                                 port=MASTER_CONFIG["port"],
                                 user='user0',
                                 password='mysql',
                                 database='sakila',
                                 charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)

    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM store LIMIT 25')

            result = cursor.fetchall()
            print(result)

    return make_response(route_type="normal",
                         ip=MASTER_CONFIG['ip'],
                         server_name=MASTER_CONFIG['name'],
                         query_response=result)


@app.route('/custom')
def custom_endpoint():
    # default to master
    min_ping_config = MASTER_CONFIG
    min_ping = ping_instance(MASTER_CONFIG["ip"])

    # ping the endpoints, and forward to the right one
    for slave_config in SLAVE_CONFIGS:
        instance_ping = ping_instance(slave_config["ip"])
        if instance_ping < min_ping:
            min_ping = instance_ping
            min_ping_config = {
                "ip": "127.0.0.1", "port": slave_config["port"], "name": slave_config["name"]}

    print(f"Redirecting to instance: {min_ping_config}")

    connection = pymysql.connect(host=min_ping_config["ip"],
                                 port=min_ping_config["port"],
                                 user='user0',
                                 password='mysql',
                                 database='sakila',
                                 charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)

    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM store LIMIT 25')
            result = cursor.fetchall()
            print(result)

    return make_response(route_type="custom",
                         ip=min_ping_config['ip'],
                         server_name=min_ping_config['name'],
                         query_response=result)


@app.route('/random')
def random_endpoint():
    # choose a random slave
    config = random.choice(SLAVE_CONFIGS)

    # connect to the database through ssh tunnelling
    connection = pymysql.connect(host="127.0.0.1",
                                 port=config["port"],
                                 user='user0',
                                 password='mysql',
                                 database='sakila',
                                 charset='utf8mb4',
                                 cursorclass=pymysql.cursors.DictCursor)

    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM store LIMIT 25')
            result = cursor.fetchall()
            print(result)

    return make_response(route_type="random",
                         ip=config['ip'],
                         server_name=config['name'],
                         query_response=result)
