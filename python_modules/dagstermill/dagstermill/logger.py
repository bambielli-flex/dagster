import copy
import json
import logging
import sqlite3
import threading
import time

from dagster import check, seven
from dagster.core.log_manager import DagsterLogManager
from dagster.utils import safe_isfile


CREATE_LOG_TABLE_STATEMENT = '''create table if not exists logs (
    timestamp integer primary key asc,
    json_log text
)
'''

INSERT_LOG_RECORD_STATEMENT = '''insert into logs (json_log) values (
    '{json_log}'
)
'''

RETRIEVE_LOG_RECORDS_STATEMENT = '''select * from logs
    where timestamp >= {timestamp}
    order by timestamp asc
'''


class JsonSqlite3Handler(logging.Handler):
    def __init__(self, sqlite_db_path):
        check.str_param(sqlite_db_path, 'sqlite_db_path')
        self.sqlite_db_path = sqlite_db_path

        if not safe_isfile(self.sqlite_db_path):
            with open(self.sqlite_db_path, 'w') as _fd:
                pass

        self.conn = sqlite3.connect(self.sqlite_db_path)
        self.cursor = self.conn.cursor()
        self.cursor.execute(CREATE_LOG_TABLE_STATEMENT)
        self.conn.commit()

        super(JsonSqlite3Handler, self).__init__()


    def emit(self, record):
        try:
            log_dict = copy.copy(record.__dict__)
            self.cursor.execute(
                INSERT_LOG_RECORD_STATEMENT.format(json_log=seven.json.dumps(log_dict))
            )
            self.conn.commit()

        except Exception as e:  # pylint: disable=W0703
            logging.critical('Error during logging!')
            logging.exception(str(e))


class JsonSqlite3LogWatcher(object):
    def __init__(self, sqlite_db_path, log_manager, is_done):
        check.str_param(sqlite_db_path, 'sqlite_db_path')
        check.inst_param(log_manager, 'log_manager', DagsterLogManager)
        check.inst_param(is_done, 'is_done', threading.Event)

        self.sqlite_db_path = sqlite_db_path
        self.conn = sqlite3.connect(self.sqlite_db_path)
        self.cursor = self.conn.cursor()
        self.last_timestamp = 0
        self.log_manager = log_manager
        self.is_done = is_done

    def watch(self):
        last_pass = False
        while True:
            res = self.cursor.execute(
                RETRIEVE_LOG_RECORDS_STATEMENT.format(timestamp=self.last_timestamp)
            ).fetchall()
            if res:
                self.last_timestamp = res[-1][0] + 1
                json_records = [r[1] for r in res]
                for json_record in json_records:
                    record = json.loads(json_record)
                    level = record.pop('levelno')
                    del record['levelname']

                    # Retrieve the original message from the formatted multiline message
                    msg = record.pop('msg')
                    message = [
                        y
                        for y
                        in  [x.strip().split(' = ') for x in msg.split('\n') if x]
                        if lambda x: x[0] == 'orig_message'][0][1].strip('"')

                    # Pop the reserved keys

                    reserved_keys = ['extra', 'exc_info']
                    for key in reserved_keys:
                        if key in record:
                            del record[key]

                    self.log_manager._log(level, message, record)  # pylint: disable=protected-access
            time.sleep(1)
            if last_pass:
                break
            if self.is_done.is_set():
                last_pass = True
