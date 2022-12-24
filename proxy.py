#!/usr/bin/python
from pythonping import ping
from sshtunnel import SSHTunnelForwarder
from flask import Flask, Response
import random
import json
import pymysql.cursors
from typing import Dict, List
import atexit

class MySQLCluster:
    def __init__(self, masters: Dict[str, str], slaves: List[Dict[str, str]]):
        self.masters = masters
        self.slaves = slaves

        # setup sshtunnels
        self.servers = []
        for slave_config in self.slaves:
            ip_forwarding = (slave_config["Adress"], 22)
            server = SSHTunnelForwarder(ip_forwarding,
                ssh_pkey="/home/ubuntu/private_key.pem",
                ssh_username="ubuntu",
                local_bind_address=('127.0.0.1', slave_config["Port"]),
                allow_agent=False,
                remote_bind_address=(self.masters["Adress"], self.masters["Port"]))
            server.start()
            self.servers.append(server)

    def close(self):
        # close sshtunnels
        for server in self.servers:
            server.stop()

    def ping_instance(self, host: str) -> float:
        """
        Pings the given instance and returns the average round-trip time.
        
        :param host: The IP address of the instance to ping.
        :return: The average round-trip time in milliseconds.
        """
        ping_result = ping(target=host)
        avg_ping = ping_result.rtt_avg_ms
        return avg_ping

    def get_server_with_lowest_ping(self) -> Dict[str, str]:
        # default to master
        min_ping_config = self.masters
        min_ping = self.ping_instance(self.masters["Adress"])

        # ping the endpoints, and return the one with the lowest ping time
        for slave_config in self.slaves:
            instance_ping = self.ping_instance(slave_config["Adress"])
            if instance_ping < min_ping:
                min_ping = instance_ping
                min_ping_config = {
                    "Adress": "127.0.0.1", "Port": slave_config["Port"], "Name": slave_config["Name"]}

        return min_ping_config
    
    def get_random_server(self) -> Dict[str, str]:
        return random.choice(self.slaves)


    def execute_query(self, query: str, server_config: Dict[str, str]) -> List[Dict[str, str]]:
        connection = pymysql.connect(host=server_config["Adress"],
                                     port=server_config["Port"],
                                     user='user0',
                                     password='mysql',
                                     database='sakila',
                                     charset='utf8mb4',
                                     cursorclass=pymysql.cursors.DictCursor)

        with connection:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
        return result



def responseQuery(route_type: str, ip: str, server_name: str, query_response: List[Dict[str, str]]) -> Response:
    """
    Makes a JSON response for the given route type, database server configuration, and query response.
    
    :param route_type: The type of route.
    :param config: The DatabaseConfig object representing the configuration of the database server.
    :param query_response: The response to the query.
    :return: A Flask Response object.
    """
    json_response = json.dumps({
        "source": server_name,
        "responseBody": str(query_response)
    })
    return Response(json_response, mimetype='application/json')

masters = {
    "Name": "master",
    "Adress": "44.201.120.181",
    "Port": 3306
}

slaves = [
    {"Name": "slave1", "Adress": "54.211.6.184" , "Port": 5001},
    {"Name": "slave2", "Adress": "44.212.70.94" , "Port": 5002},
    {"Name": "slave3", "Adress": "54.158.97.142", "Port": 5003},
]

# create MySQLCluster instance
mysql_cluster = MySQLCluster(masters, slaves)

# flask Application : defines our endpoints and their logic
app = Flask(__name__)


@app.route('/normal')
def normal_query():
    """
    Handles a normal query by forwarding it directly to the master database server.
    
    :return: A Flask Response object.
    """
    result = mysql_cluster.execute_query('SELECT * FROM store LIMIT 25', mysql_cluster.masters)
    return responseQuery(route_type="normal",
                         ip=mysql_cluster.masters['Adress'],
                         server_name=mysql_cluster.masters['Name'],
                         query_response=result)


@app.route('/custom')
def custom_query():
    """
     Executes a custom query on the given database server through the SSH tunnel.
    select the server with the lowest ping time
    
    :return: A tuple containing the response to the query and the time it took to execute the query.
    """
    min_ping_config = mysql_cluster.get_server_with_lowest_ping()

    # execute query on selected server
    result = mysql_cluster.execute_query('SELECT * FROM store LIMIT 25', min_ping_config)
    return responseQuery(route_type="custom",
                         ip=min_ping_config['Adress'],
                         server_name=min_ping_config['Name'],
                         query_response=result)

@app.route('/random')
def random_query():
    """
    Connects to a random database server and retrieves data from a table.
    """
    random_server_config = mysql_cluster.get_random_server()

    # execute query on selected server
    result = mysql_cluster.execute_query('SELECT * FROM store LIMIT 25', random_server_config)
    return responseQuery(route_type="random",
                         ip=random_server_config['Adress'],
                         server_name=random_server_config['Name'],
                         query_response=result)

# close MySQLCluster instance when the program exits
atexit.register(mysql_cluster.close)