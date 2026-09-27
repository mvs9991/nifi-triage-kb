import sys
import pymysql

DB_HOST = "10.20.30.40"
password = "hunter2"
conn = pymysql.connect(host=DB_HOST, user="etl", password=password, database="meta")


def enrich(order_id):
    cur = conn.cursor()
    cur.execute("SELECT name, region FROM customers WHERE id = %s", (order_id,))
    return cur.fetchone()


def main():
    print(enrich(sys.argv[1]))
