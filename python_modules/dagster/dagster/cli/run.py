import datetime
import click

from dagster.core.runs import FileStorageBasedRunStorage


def create_run_cli_group():
    group = click.Group(name="run")
    group.add_command(run_list_command)
    group.add_command(run_nuke_command)
    return group


@click.command(name='list', help='List the runs in this dagster installation.')
def run_list_command():
    storage = FileStorageBasedRunStorage.default()
    for run_meta in storage.get_run_metas():
        print('Run: {}'.format(run_meta.run_id))
        print('     Pipeline: {}'.format(run_meta.pipeline_name))
        print('     Start time: {}'.format(datetime.datetime.fromtimestamp(run_meta.timestamp)))


@click.command(name='nuke', help='Eliminate all run history. Warning: Cannot be undone')
def run_nuke_command():
    storage = FileStorageBasedRunStorage.default()
    storage.nuke()
    print('Deleted all run history')