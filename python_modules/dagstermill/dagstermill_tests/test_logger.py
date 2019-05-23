import logging
import sqlite3
import tempfile
import threading
import uuid

from dagster import PipelineDefinition, seven
from dagster.core.execution.context.logger import InitLoggerContext
from dagster.core.log_manager import DagsterLogManager
from dagster.utils.log import construct_single_handler_logger

from dagstermill.logger import JsonSqlite3Handler, JsonSqlite3LogWatcher


TEST_LOG_RECORDS = []


class TestHandler(logging.Handler):
    def emit(self, record):
        # Issue is that we still have dagster_meta on the LogRecord:
        # https://docs.python.org/3/library/logging.html#logrecord-objects
        # makeLogRecord()
        global TEST_LOG_RECORDS
        import pdb; pdb.set_trace()
        if 'dagster_meta' in record.__dict__:
            dagster_meta = record.__dict__.pop('dagster_meta')
            if 'dagster_meta' in dagster_meta:
                del dagster_meta['dagster_meta']
            record.__dict__ = dict(record.__dict__, **dagster_meta)
        TEST_LOG_RECORDS.append(record)


def dummy_init_logger_context(logger_def, run_id):
    return InitLoggerContext({}, PipelineDefinition([]), logger_def, run_id)


def test_json_sqlite3_handler():
    run_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile() as sqlite3_db:
        sqlite3_db_path = sqlite3_db.name

    sqlite3_handler = JsonSqlite3Handler(sqlite3_db_path)
    sqlite3_logger_def = construct_single_handler_logger(
        'sqlite3', 'debug', sqlite3_handler
    )
    sqlite3_logger = sqlite3_logger_def.logger_fn(
        dummy_init_logger_context(sqlite3_logger_def, run_id)
    )
    sqlite3_log_manager = DagsterLogManager(run_id, {}, [sqlite3_logger])

    for i in range(1000):
        sqlite3_log_manager.info('Testing ' + str(i))

    conn = sqlite3.connect(sqlite3_db_path)
    cursor = conn.cursor()
    count = cursor.execute('select count(1) from logs').fetchall()
    assert count[0][0] == 1000


def test_json_sqlite3_watcher():
    run_id = str(uuid.uuid4())
    with tempfile.NamedTemporaryFile() as sqlite3_db:
        sqlite3_db_path = sqlite3_db.name

    sqlite3_handler = JsonSqlite3Handler(sqlite3_db_path)
    sqlite3_logger_def = construct_single_handler_logger(
        'sqlite3', 'debug', sqlite3_handler
    )
    sqlite3_logger = sqlite3_logger_def.logger_fn(
        dummy_init_logger_context(sqlite3_logger_def, run_id)
    )
    sqlite3_log_manager = DagsterLogManager(run_id, {}, [sqlite3_logger])

    for i in range(1000):
        sqlite3_log_manager.info('Testing ' + str(i))

    conn = sqlite3.connect(sqlite3_db_path)
    cursor = conn.cursor()
    count = cursor.execute('select count(1) from logs').fetchall()
    assert count[0][0] == 1000

    is_done = threading.Event()
    is_done.set()

    test_handler = TestHandler()
    test_logger_def = construct_single_handler_logger('test', 'debug', test_handler)
    test_logger = test_logger_def.logger_fn(dummy_init_logger_context(test_logger_def, run_id))
    sqlite3_watcher_log_manager = DagsterLogManager(run_id, {}, [test_logger])
    sqlite3_watcher = JsonSqlite3LogWatcher(sqlite3_db_path, sqlite3_watcher_log_manager, is_done)

    sqlite3_watcher.watch()

    assert len(TEST_LOG_RECORDS) == 1000

    records = cursor.execute('select * from logs').fetchall()
    for i, record in enumerate(records):
        json_record = record[1]
        assert json_record == seven.json.dumps(TEST_LOG_RECORDS[i].__dict__)


def test_concurrent_logging():
    run_id = str(uuid.uuid4())

    with tempfile.NamedTemporaryFile() as sqlite3_db:

        sqlite3_db_path = sqlite3_db.name

        is_done = threading.Event()

        def sqlite3_thread_target(sqlite3_db_path):
            sqlite3_handler = JsonSqlite3Handler(sqlite3_db_path)
            sqlite3_logger_def = construct_single_handler_logger(
                'sqlite3', 'debug', sqlite3_handler
            )
            sqlite3_logger = sqlite3_logger_def.logger_fn(
                dummy_init_logger_context(sqlite3_logger_def, run_id)
            )
            sqlite3_log_manager = DagsterLogManager(run_id, {}, [sqlite3_logger])

            for i in range(1000):
                sqlite3_log_manager.info('Testing ' + str(i))

        def test_thread_target(sqlite3_db_path, is_done):
            test_handler = TestHandler()
            test_logger_def = construct_single_handler_logger('test', 'debug', test_handler)
            test_logger = test_logger_def.logger_fn(dummy_init_logger_context(test_logger_def, run_id))
            test_log_manager = DagsterLogManager(run_id, {}, [test_logger])
            test_log_watcher = JsonSqlite3LogWatcher(sqlite3_db_path, test_log_manager, is_done)
            test_log_watcher.watch()

        sqlite_3_thread = threading.Thread(
            target=sqlite3_thread_target, args=(sqlite3_db_path,)
        )

        test_thread = threading.Thread(
            target=test_thread_target, args=(sqlite3_db_path, is_done)
        )

        sqlite_3_thread.start()
        test_thread.start()

        try:
            sqlite_3_thread.join()
        finally:
            is_done.set()

        assert is_done.is_set()
        assert TEST_LOG_RECORDS
